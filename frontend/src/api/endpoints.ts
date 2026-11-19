import { apiRequest, buildQuery } from './client';
import type {
  AnalyticsResponse,
  ConnectionCheckResult,
  DataSource,
  HealthCheck,
  InferencePayload,
  InferenceRecord,
  InfrastructureResponse,
  LogListItem,
  Model,
  ModelCreatePayload,
  ModelUpdatePayload,
  OverviewResponse,
  Page,
  RequestSource,
  RequestStatus,
  SystemInfo,
  TimeWindow,
  UsageHistoryResponse,
} from './types';

export const getSystemInfo = (signal?: AbortSignal) => apiRequest<SystemInfo>('/api/system/info', { signal });

export const getOverview = (window: TimeWindow, dataSource: DataSource, signal?: AbortSignal) =>
  apiRequest<OverviewResponse>(`/api/overview${buildQuery({ window, data_source: dataSource })}`, { signal });

export const getAnalytics = (
  params: { window: TimeWindow; dataSource: DataSource; modelId?: string | null },
  signal?: AbortSignal,
) =>
  apiRequest<AnalyticsResponse>(
    `/api/analytics${buildQuery({ window: params.window, data_source: params.dataSource, model_id: params.modelId })}`,
    { signal },
  );

export const listModels = (signal?: AbortSignal) => apiRequest<Model[]>('/api/models', { signal });

export const createModel = (payload: ModelCreatePayload) =>
  apiRequest<Model>('/api/models', { method: 'POST', body: payload });

export const updateModel = (id: string, payload: ModelUpdatePayload) =>
  apiRequest<Model>(`/api/models/${id}`, { method: 'PATCH', body: payload });

export const deleteModel = (id: string) => apiRequest<void>(`/api/models/${id}`, { method: 'DELETE' });

export const checkModelConnection = (id: string) =>
  apiRequest<ConnectionCheckResult>(`/api/models/${id}/check`, { method: 'POST' });

export const listHealthChecks = (id: string, limit = 10, signal?: AbortSignal) =>
  apiRequest<HealthCheck[]>(`/api/models/${id}/health-checks${buildQuery({ limit })}`, { signal });

export const runInference = (payload: InferencePayload) =>
  apiRequest<InferenceRecord>('/api/inference', { method: 'POST', body: payload });

export const getInfrastructure = (signal?: AbortSignal) =>
  apiRequest<InfrastructureResponse>('/api/infrastructure', { signal });

export const getUsageHistory = (signal?: AbortSignal) =>
  apiRequest<UsageHistoryResponse>('/api/infrastructure/history', { signal });

export interface LogQuery {
  search?: string;
  modelId?: string;
  status?: RequestStatus | '';
  source?: RequestSource | '';
  dataSource?: DataSource;
  window?: TimeWindow | '';
  page?: number;
  pageSize?: number;
}

export const listLogs = (query: LogQuery, signal?: AbortSignal) =>
  apiRequest<Page<LogListItem>>(
    `/api/logs${buildQuery({
      search: query.search,
      model_id: query.modelId,
      status: query.status,
      source: query.source,
      data_source: query.dataSource,
      window: query.window,
      page: query.page,
      page_size: query.pageSize,
    })}`,
    { signal },
  );

export const getLog = (id: string, signal?: AbortSignal) =>
  apiRequest<InferenceRecord>(`/api/logs/${id}`, { signal });
