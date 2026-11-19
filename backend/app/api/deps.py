"""FastAPI dependencies. Long-lived objects are created in the app lifespan and kept on
app.state, so tests can build an app with their own settings and HTTP transport."""

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.monitoring.sampler import SystemSampler
from app.providers.registry import ProviderRegistry
from app.schemas.common import DataSource
from app.security import SecretBox


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_providers(request: Request) -> ProviderRegistry:
    return request.app.state.providers


def get_secret_box(request: Request) -> SecretBox:
    return request.app.state.secret_box


def get_sampler(request: Request) -> SystemSampler:
    return request.app.state.sampler


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def resolve_data_source(
    settings: Annotated[Settings, Depends(get_settings)],
    data_source: Annotated[DataSource | None, Query(description="real, demo or all")] = None,
) -> DataSource:
    """Default to real data only, unless the deployment runs in demo mode."""
    if data_source is not None:
        return data_source
    return DataSource.ALL if settings.demo_mode else DataSource.REAL


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ProvidersDep = Annotated[ProviderRegistry, Depends(get_providers)]
SecretBoxDep = Annotated[SecretBox, Depends(get_secret_box)]
SamplerDep = Annotated[SystemSampler, Depends(get_sampler)]
HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
DataSourceDep = Annotated[DataSource, Depends(resolve_data_source)]
