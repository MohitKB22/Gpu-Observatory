"""Latency, throughput and error analytics computed from recorded requests.

Aggregation happens in PostgreSQL (percentile_cont, FILTER clauses) so the API never pulls
raw request rows into Python. Latency percentiles and averages use successful requests only.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, Row, Select, extract, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InferenceRequest, RequestMetrics
from app.models.enums import RequestStatus, TokenCountSource
from app.schemas.analytics import (
    AnalyticsResponse,
    DataScope,
    LatencyPercentiles,
    ModelComparisonRow,
    SummaryStats,
    TimeseriesPoint,
)
from app.schemas.common import DataSource, TimeWindow

_succeeded = InferenceRequest.status == RequestStatus.SUCCESS.value
_failed = InferenceRequest.status == RequestStatus.ERROR.value


@dataclass(frozen=True)
class AnalyticsQuery:
    start: datetime
    end: datetime
    data_source: DataSource
    model_id: uuid.UUID | None = None

    @classmethod
    def for_window(
        cls, window: TimeWindow, data_source: DataSource, model_id: uuid.UUID | None = None, now: datetime | None = None
    ) -> "AnalyticsQuery":
        end = now or datetime.now(UTC)
        return cls(start=end - window.duration, end=end, data_source=data_source, model_id=model_id)

    def previous_period(self) -> "AnalyticsQuery":
        length = self.end - self.start
        return AnalyticsQuery(self.start - length, self.start, self.data_source, self.model_id)

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()


async def build_analytics(
    session: AsyncSession, window: TimeWindow, data_source: DataSource, model_id: uuid.UUID | None
) -> AnalyticsResponse:
    query = AnalyticsQuery.for_window(window, data_source, model_id)
    summary_row = await _fetch_summary_row(session, query)
    return AnalyticsResponse(
        window=window,
        start=query.start,
        end=query.end,
        bucket_seconds=window.bucket_seconds,
        scope=data_scope(summary_row, data_source),
        summary=summary_from_row(summary_row, query.seconds),
        timeseries=await fetch_timeseries(session, query, window.bucket_seconds),
        models=await fetch_model_comparison(session, query),
    )


async def fetch_summary(session: AsyncSession, query: AnalyticsQuery) -> tuple[SummaryStats, DataScope]:
    row = await _fetch_summary_row(session, query)
    return summary_from_row(row, query.seconds), data_scope(row, query.data_source)


async def fetch_timeseries(session: AsyncSession, query: AnalyticsQuery, bucket_seconds: int) -> list[TimeseriesPoint]:
    # bucket_seconds is an int from TimeWindow, so inlining it is safe. Inlining (rather than
    # binding) keeps the SELECT and GROUP BY expressions identical for PostgreSQL.
    bucket_size = literal_column(str(int(bucket_seconds)))
    bucket_epoch = (func.floor(extract("epoch", InferenceRequest.created_at) / bucket_size) * bucket_size).label(
        "bucket_epoch"
    )
    statement = _base_select(query, bucket_epoch, *_aggregate_columns()).group_by(bucket_epoch).order_by(bucket_epoch)
    rows_by_bucket = {int(row.bucket_epoch): row for row in await session.execute(statement)}

    points = []
    first_bucket = int(query.start.timestamp()) // bucket_seconds * bucket_seconds
    for bucket_start in range(first_bucket, int(query.end.timestamp()) + 1, bucket_seconds):
        row = rows_by_bucket.get(bucket_start)
        points.append(_timeseries_point(bucket_start, row, bucket_seconds))
    return points


async def fetch_model_comparison(session: AsyncSession, query: AnalyticsQuery) -> list[ModelComparisonRow]:
    statement = (
        _base_select(
            query,
            InferenceRequest.model_id,
            InferenceRequest.model_name,
            InferenceRequest.provider,
            func.bool_or(InferenceRequest.is_demo).label("is_demo"),
            *_aggregate_columns(),
        )
        .group_by(InferenceRequest.model_id, InferenceRequest.model_name, InferenceRequest.provider)
        .order_by(func.count().desc())
    )
    return [
        ModelComparisonRow(
            model_id=row.model_id,
            model_name=row.model_name,
            provider=row.provider,
            is_demo=row.is_demo,
            stats=summary_from_row(row, query.seconds),
        )
        for row in await session.execute(statement)
    ]


def summary_from_row(row: Row, seconds: float) -> SummaryStats:
    requests = row.requests or 0
    tokens = int(row.tokens or 0)
    return SummaryStats(
        total_requests=requests,
        error_requests=row.errors or 0,
        error_rate=(row.errors / requests) if requests else None,
        requests_per_second=requests / seconds if seconds else 0.0,
        latency=LatencyPercentiles(p50_ms=row.p50, p95_ms=row.p95, p99_ms=row.p99),
        avg_latency_ms=row.avg_latency,
        avg_tokens_per_second=row.avg_tps,
        token_throughput_per_second=tokens / seconds if seconds else 0.0,
        total_tokens=tokens,
        exact_token_share=(row.exact_counts / row.successes) if row.successes else None,
    )


def data_scope(row: Row, data_source: DataSource) -> DataScope:
    demo = row.demo_requests or 0
    return DataScope(
        data_source=data_source,
        demo_requests=demo,
        real_requests=(row.requests or 0) - demo,
        includes_demo_data=demo > 0,
    )


async def _fetch_summary_row(session: AsyncSession, query: AnalyticsQuery) -> Row:
    return (await session.execute(_base_select(query, *_aggregate_columns()))).one()


def _base_select(query: AnalyticsQuery, *columns: ColumnElement) -> Select:
    statement = (
        select(*columns)
        .select_from(InferenceRequest)
        .join(RequestMetrics, RequestMetrics.request_id == InferenceRequest.id)
        .where(InferenceRequest.created_at >= query.start, InferenceRequest.created_at < query.end)
    )
    if query.data_source == DataSource.REAL:
        statement = statement.where(InferenceRequest.is_demo.is_(False))
    elif query.data_source == DataSource.DEMO:
        statement = statement.where(InferenceRequest.is_demo.is_(True))
    if query.model_id is not None:
        statement = statement.where(InferenceRequest.model_id == query.model_id)
    return statement


def _aggregate_columns() -> list[ColumnElement]:
    latency = RequestMetrics.latency_ms
    return [
        func.count().label("requests"),
        func.count().filter(_failed).label("errors"),
        func.count().filter(_succeeded).label("successes"),
        func.percentile_cont(0.50).within_group(latency).filter(_succeeded).label("p50"),
        func.percentile_cont(0.95).within_group(latency).filter(_succeeded).label("p95"),
        func.percentile_cont(0.99).within_group(latency).filter(_succeeded).label("p99"),
        func.avg(latency).filter(_succeeded).label("avg_latency"),
        func.avg(RequestMetrics.tokens_per_second).filter(_succeeded).label("avg_tps"),
        func.coalesce(func.sum(RequestMetrics.total_tokens), 0).label("tokens"),
        func.count()
        .filter(_succeeded, RequestMetrics.token_count_source == TokenCountSource.EXACT.value)
        .label("exact_counts"),
        func.count().filter(InferenceRequest.is_demo.is_(True)).label("demo_requests"),
    ]


def _timeseries_point(bucket_start: int, row: Row | None, bucket_seconds: int) -> TimeseriesPoint:
    timestamp = datetime.fromtimestamp(bucket_start, tz=UTC)
    if row is None:
        return TimeseriesPoint(
            timestamp=timestamp,
            requests=0,
            errors=0,
            error_rate=None,
            requests_per_second=0.0,
            p50_ms=None,
            p95_ms=None,
            p99_ms=None,
            tokens=0,
            token_throughput_per_second=0.0,
            avg_tokens_per_second=None,
        )
    tokens = int(row.tokens or 0)
    return TimeseriesPoint(
        timestamp=timestamp,
        requests=row.requests,
        errors=row.errors,
        error_rate=row.errors / row.requests if row.requests else None,
        requests_per_second=row.requests / bucket_seconds,
        p50_ms=row.p50,
        p95_ms=row.p95,
        p99_ms=row.p99,
        tokens=tokens,
        token_throughput_per_second=tokens / bucket_seconds,
        avg_tokens_per_second=row.avg_tps,
    )
