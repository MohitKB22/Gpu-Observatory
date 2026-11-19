import { useState } from 'react';

import { getAnalytics, listModels } from '@/api/endpoints';
import type { AnalyticsResponse, TimeWindow } from '@/api/types';
import { CHART_COLORS } from '@/components/charts/chartTheme';
import { ModelLatencyChart } from '@/components/charts/ModelLatencyChart';
import { LatencyPercentilesChart, MetricChart } from '@/components/charts/TimeSeriesCharts';
import { PageHeader } from '@/components/layout/PageHeader';
import { Card, CardHeader } from '@/components/ui/Card';
import { RefreshControl, WindowSelector } from '@/components/ui/Controls';
import { Select } from '@/components/ui/Form';
import { StatCard } from '@/components/ui/StatCard';
import { DemoDataNotice, EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { useDataSource } from '@/context/DataSourceContext';
import { useApiQuery } from '@/hooks/useApiQuery';
import { windowLabel } from '@/lib/constants';
import {
  formatCompact,
  formatLatency,
  formatPercent,
  formatRequestRate,
  formatTokensPerSecond,
} from '@/lib/format';
import { ModelComparisonTable } from './ModelComparisonTable';

export default function AnalyticsPage() {
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('24h');
  const [modelId, setModelId] = useState('');
  const { dataSource, ready } = useDataSource();
  const models = useApiQuery(listModels, []);
  const query = useApiQuery(
    (signal) => getAnalytics({ window: timeWindow, dataSource, modelId: modelId || null }, signal),
    [timeWindow, dataSource, modelId],
    { refreshIntervalMs: 30_000, enabled: ready },
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Performance Analytics"
        description="Latency percentiles, throughput and errors computed from recorded requests."
        actions={
          <>
            <label htmlFor="analytics-model" className="sr-only">
              Model
            </label>
            <Select
              id="analytics-model"
              value={modelId}
              onChange={(event) => setModelId(event.target.value)}
              className="h-8 w-44 text-xs"
            >
              <option value="">All models</option>
              {(models.data ?? []).map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </Select>
            <WindowSelector value={timeWindow} onChange={setTimeWindow} />
            <RefreshControl updatedAt={query.updatedAt} isFetching={query.isFetching} onRefresh={query.refetch} />
          </>
        }
      />

      {query.error && !query.data ? (
        <ErrorState error={query.error} onRetry={query.refetch} />
      ) : !query.data ? (
        <AnalyticsSkeleton />
      ) : (
        <AnalyticsContent data={query.data} />
      )}
    </div>
  );
}

function AnalyticsContent({ data }: { data: AnalyticsResponse }) {
  const { summary } = data;
  const period = windowLabel(data.window);

  if (summary.total_requests === 0) {
    return (
      <>
        <DemoDataNotice scope={data.scope} />
        <Card>
          <EmptyState
            title={`No requests in the ${period}`}
            description="Analytics are calculated from recorded requests. Run prompts in the Playground or widen the time window."
          />
        </Card>
      </>
    );
  }

  const exactShare = summary.exact_token_share;
  return (
    <>
      <DemoDataNotice scope={data.scope} />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard size="compact" label="P50 latency" value={formatLatency(summary.latency.p50_ms)} hint="median" />
        <StatCard size="compact" label="P95 latency" value={formatLatency(summary.latency.p95_ms)} />
        <StatCard size="compact" label="P99 latency" value={formatLatency(summary.latency.p99_ms)} />
        <StatCard size="compact" label="Request rate" value={formatRequestRate(summary.requests_per_second)} hint={`${formatCompact(summary.total_requests)} total`} />
        <StatCard
          size="compact"
          label="Token throughput"
          value={formatTokensPerSecond(summary.token_throughput_per_second)}
          hint={
            exactShare === null
              ? undefined
              : exactShare === 1
                ? 'all counts exact'
                : `${formatPercent(1 - exactShare, 0)} estimated`
          }
        />
        <StatCard size="compact" label="Error rate" value={formatPercent(summary.error_rate)} hint={`${formatCompact(summary.error_requests)} errors`} />
      </div>

      <Card>
        <CardHeader
          title="Latency percentiles"
          description={`Successful requests only, ${period}. Line style distinguishes P50 (solid), P95 (dashed) and P99 (dotted).`}
        />
        <div className="px-2 pb-3">
          <LatencyPercentilesChart points={data.timeseries} bucketSeconds={data.bucket_seconds} height={280} />
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Request rate" description="Requests per second, per interval" />
          <div className="px-2 pb-3">
            <MetricChart
              points={data.timeseries}
              bucketSeconds={data.bucket_seconds}
              dataKey="requests_per_second"
              name="Requests/s"
              color={CHART_COLORS.blue}
              format={(value) => value.toFixed(value < 1 ? 3 : 1)}
              variant="bar"
            />
          </div>
        </Card>
        <Card>
          <CardHeader title="Token throughput" description="Prompt + completion tokens per second" />
          <div className="px-2 pb-3">
            <MetricChart
              points={data.timeseries}
              bucketSeconds={data.bucket_seconds}
              dataKey="token_throughput_per_second"
              name="Tokens/s"
              color={CHART_COLORS.violet}
              format={(value) => formatCompact(value)}
            />
          </div>
        </Card>
        <Card>
          <CardHeader title="Error rate" description="Failed requests as a share of all requests" />
          <div className="px-2 pb-3">
            <MetricChart
              points={data.timeseries}
              bucketSeconds={data.bucket_seconds}
              dataKey="error_rate"
              name="Error rate"
              color={CHART_COLORS.red}
              format={(value) => formatPercent(value, 0)}
            />
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Model comparison" description={`All metrics, ${period}`} />
        <ModelComparisonTable rows={data.models} />
      </Card>

      <Card>
        <CardHeader title="P95 latency by model" description="Slowest first; demo models in violet" />
        <div className="px-2 pb-3">
          <ModelLatencyChart rows={data.models} />
        </div>
      </Card>
    </>
  );
}

function AnalyticsSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading analytics">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-80" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}
