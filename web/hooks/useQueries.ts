'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type QueryParams } from '@/lib/api';
import { useAppStore } from '@/stores/useAppStore';
import type {
  AgentCapabilities,
  AgentChatResponse,
  Alert,
  AlertRule,
  AlertSummary,
  Anomaly,
  AuthConfig,
  BatchAnalysis,
  ComparisonResponse,
  CostSummary,
  CurrentUser,
  DemoScenarioInfo,
  DemoState,
  Deployment,
  Diagnosis,
  DiagnosisReport,
  Gpu,
  GpuAvailability,
  GpuDetail,
  InferenceRequestRow,
  InferenceSummary,
  LatencyBucket,
  MLModel,
  ModelPerformance,
  OverviewResponse,
  Page,
  PricingProfile,
  SystemSnapshot,
  TimeSeriesResponse,
  Workload,
  WorkloadProfileInfo,
} from '@/lib/types';

/** Shared query scope: every request is namespaced by data source and range. */
function useScope() {
  const { dataSource, range, refreshMs } = useAppStore();
  return { dataSource, range, refreshMs: refreshMs > 0 ? refreshMs : false as const };
}

function params(extra: QueryParams = {}, dataSource?: string): QueryParams {
  return { ...(dataSource ? { source: dataSource } : {}), ...extra };
}

export function useOverview() {
  const { dataSource, range, refreshMs } = useScope();
  return useQuery({
    queryKey: ['overview', dataSource, range],
    queryFn: ({ signal }) =>
      api.get<OverviewResponse>('/api/v1/overview', params({ range }, dataSource), signal),
    refetchInterval: refreshMs,
  });
}

export function useGpus() {
  const { dataSource, refreshMs } = useScope();
  return useQuery({
    queryKey: ['gpus', dataSource],
    queryFn: ({ signal }) => api.get<Gpu[]>('/api/v1/gpus', params({}, dataSource), signal),
    refetchInterval: refreshMs,
  });
}

export function useGpuAvailability() {
  const { dataSource } = useScope();
  return useQuery({
    queryKey: ['gpu-availability', dataSource],
    queryFn: ({ signal }) =>
      api.get<GpuAvailability>('/api/v1/gpus/availability', params({}, dataSource), signal),
  });
}

export function useGpuDetail(gpuId: string | null) {
  const { dataSource, refreshMs } = useScope();
  return useQuery({
    queryKey: ['gpu-detail', dataSource, gpuId],
    queryFn: ({ signal }) =>
      api.get<GpuDetail>(`/api/v1/gpus/${gpuId}`, params({}, dataSource), signal),
    enabled: Boolean(gpuId),
    refetchInterval: refreshMs,
  });
}

export function useGpuSeries(metrics: string, gpuIds?: string[]) {
  const { dataSource, range, refreshMs } = useScope();
  return useQuery({
    queryKey: ['gpu-series', dataSource, range, metrics, gpuIds?.join(',') ?? 'all'],
    queryFn: ({ signal }) =>
      api.get<TimeSeriesResponse>(
        '/api/v1/gpus/series/timeseries',
        params({ range, metrics, gpu_ids: gpuIds?.join(',') }, dataSource),
        signal,
      ),
    refetchInterval: refreshMs,
  });
}

export function useSystemMetrics() {
  const { dataSource, refreshMs } = useScope();
  return useQuery({
    queryKey: ['system-metrics', dataSource],
    queryFn: ({ signal }) =>
      api.get<SystemSnapshot>('/api/v1/system/metrics', params({}, dataSource), signal),
    refetchInterval: refreshMs,
  });
}

export function useSystemSeries(metrics = 'cpu_utilization_pct,ram_utilization_pct') {
  const { dataSource, range, refreshMs } = useScope();
  return useQuery({
    queryKey: ['system-series', dataSource, range, metrics],
    queryFn: ({ signal }) =>
      api.get<TimeSeriesResponse>(
        '/api/v1/system/series',
        params({ range, metrics }, dataSource),
        signal,
      ),
    refetchInterval: refreshMs,
  });
}

export function useInferenceSummary(deploymentId?: string) {
  const { dataSource, range, refreshMs } = useScope();
  return useQuery({
    queryKey: ['inference-summary', dataSource, range, deploymentId ?? 'all'],
    queryFn: ({ signal }) =>
      api.get<InferenceSummary>(
        '/api/v1/inference/metrics',
        params({ range, deployment_id: deploymentId }, dataSource),
        signal,
      ),
    refetchInterval: refreshMs,
  });
}

export function useInferenceSeries(metrics: string) {
  const { dataSource, range, refreshMs } = useScope();
  return useQuery({
    queryKey: ['inference-series', dataSource, range, metrics],
    queryFn: ({ signal }) =>
      api.get<TimeSeriesResponse>(
        '/api/v1/inference/series',
        params({ range, metrics }, dataSource),
        signal,
      ),
    refetchInterval: refreshMs,
  });
}

export function useLatencyDistribution() {
  const { dataSource, range, refreshMs } = useScope();
  return useQuery({
    queryKey: ['latency-distribution', dataSource, range],
    queryFn: ({ signal }) =>
      api.get<LatencyBucket[]>(
        '/api/v1/inference/latency',
        params({ range, bins: 24 }, dataSource),
        signal,
      ),
    refetchInterval: refreshMs,
  });
}

export function useInferenceRequests(errorsOnly: boolean, limit = 50) {
  const { dataSource, range, refreshMs } = useScope();
  return useQuery({
    queryKey: ['inference-requests', dataSource, range, errorsOnly, limit],
    queryFn: ({ signal }) =>
      api.get<Page<InferenceRequestRow>>(
        '/api/v1/inference/requests',
        params({ range, errors_only: errorsOnly, limit }, dataSource),
        signal,
      ),
    refetchInterval: refreshMs,
  });
}

export function useModels() {
  const { dataSource } = useScope();
  return useQuery({
    queryKey: ['models', dataSource],
    queryFn: ({ signal }) =>
      api.get<Page<MLModel>>('/api/v1/models', params({ limit: 200 }, dataSource), signal),
  });
}

export function useDeployments() {
  const { dataSource } = useScope();
  return useQuery({
    queryKey: ['deployments', dataSource],
    queryFn: ({ signal }) =>
      api.get<Deployment[]>('/api/v1/deployments', params({}, dataSource), signal),
  });
}

export function useModelPerformance(modelId: string | null) {
  const { dataSource, range } = useScope();
  return useQuery({
    queryKey: ['model-performance', dataSource, range, modelId],
    queryFn: ({ signal }) =>
      api.get<ModelPerformance>(
        `/api/v1/models/${modelId}/performance`,
        params({ range }, dataSource),
        signal,
      ),
    enabled: Boolean(modelId),
  });
}

export function useComparison(modelIds: string[]) {
  const { dataSource, range } = useScope();
  return useQuery({
    queryKey: ['comparison', dataSource, range, modelIds.join(',')],
    queryFn: ({ signal }) =>
      api.get<ComparisonResponse>(
        '/api/v1/comparisons/models',
        params({ range, model_ids: modelIds.join(',') }, dataSource),
        signal,
      ),
    enabled: modelIds.length >= 2,
    retry: false,
  });
}

export function useBatchAnalysis() {
  const { dataSource, range, refreshMs } = useScope();
  return useQuery({
    queryKey: ['batches', dataSource, range],
    queryFn: ({ signal }) =>
      api.get<BatchAnalysis>('/api/v1/batches', params({ range }, dataSource), signal),
    refetchInterval: refreshMs,
  });
}

export function useAnomalies() {
  const { dataSource, range, refreshMs } = useScope();
  return useQuery({
    queryKey: ['anomalies', dataSource, range],
    queryFn: ({ signal }) =>
      api.get<Page<Anomaly>>(
        '/api/v1/anomalies',
        params({ range: range === '5m' || range === '15m' ? '1h' : range, limit: 100 }, dataSource),
        signal,
      ),
    refetchInterval: refreshMs,
  });
}

export function useAlerts(state?: string) {
  const { dataSource, refreshMs } = useScope();
  return useQuery({
    queryKey: ['alerts', dataSource, state ?? 'all'],
    queryFn: ({ signal }) =>
      api.get<Page<Alert>>('/api/v1/alerts', params({ state, limit: 100 }, dataSource), signal),
    refetchInterval: refreshMs,
  });
}

export function useAlertSummary() {
  const { dataSource, refreshMs } = useScope();
  return useQuery({
    queryKey: ['alert-summary', dataSource],
    queryFn: ({ signal }) =>
      api.get<AlertSummary>('/api/v1/alerts/summary', params({}, dataSource), signal),
    refetchInterval: refreshMs,
  });
}

export function useAlertRules() {
  const { dataSource } = useScope();
  return useQuery({
    queryKey: ['alert-rules', dataSource],
    queryFn: ({ signal }) =>
      api.get<AlertRule[]>('/api/v1/alert-rules', params({}, dataSource), signal),
  });
}

export function useAcknowledgeAlert() {
  const client = useQueryClient();
  const { dataSource } = useScope();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      api.post<Alert>(`/api/v1/alerts/${id}/acknowledge`, { note: note ?? null }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['alerts', dataSource] });
      void client.invalidateQueries({ queryKey: ['alert-summary', dataSource] });
    },
  });
}

export function useResolveAlert() {
  const client = useQueryClient();
  const { dataSource } = useScope();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => api.post<Alert>(`/api/v1/alerts/${id}/resolve`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['alerts', dataSource] });
      void client.invalidateQueries({ queryKey: ['alert-summary', dataSource] });
    },
  });
}

export function useDiagnosticsHistory() {
  const { dataSource } = useScope();
  return useQuery({
    queryKey: ['diagnostics-history', dataSource],
    queryFn: ({ signal }) =>
      api.get<Page<Diagnosis>>(
        '/api/v1/diagnostics/history',
        params({ limit: 50 }, dataSource),
        signal,
      ),
  });
}

export function useRunDiagnostics() {
  const client = useQueryClient();
  const { dataSource, range } = useScope();
  return useMutation({
    mutationFn: () =>
      api.post<DiagnosisReport>(
        '/api/v1/diagnostics',
        { range, use_llm: true, persist: true },
        { source: dataSource },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['diagnostics-history', dataSource] });
    },
  });
}

export function useCost() {
  const { dataSource, range } = useScope();
  return useQuery({
    queryKey: ['cost', dataSource, range],
    queryFn: ({ signal }) =>
      api.get<CostSummary>('/api/v1/cost', params({ range }, dataSource), signal),
  });
}

export function usePricing() {
  return useQuery({
    queryKey: ['pricing'],
    queryFn: ({ signal }) => api.get<PricingProfile[]>('/api/v1/cost/pricing', {}, signal),
  });
}

export function useDemoState() {
  return useQuery({
    queryKey: ['demo-state'],
    queryFn: ({ signal }) => api.get<DemoState>('/api/v1/demo', {}, signal),
    refetchInterval: 15_000,
  });
}

export function useDemoScenarios() {
  return useQuery({
    queryKey: ['demo-scenarios'],
    queryFn: ({ signal }) => api.get<DemoScenarioInfo[]>('/api/v1/demo/scenarios', {}, signal),
  });
}

export function useSetDemoScenario() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (scenario: string) => api.post<DemoState>('/api/v1/demo/scenario', { scenario }),
    onSuccess: () => {
      void client.invalidateQueries();
    },
  });
}

export function useWorkloads() {
  return useQuery({
    queryKey: ['workloads'],
    queryFn: ({ signal }) => api.get<Page<Workload>>('/api/v1/workloads', { limit: 50 }, signal),
    refetchInterval: 5_000,
  });
}

export function useWorkloadProfiles() {
  return useQuery({
    queryKey: ['workload-profiles'],
    queryFn: ({ signal }) => api.get<WorkloadProfileInfo[]>('/api/v1/workloads/profiles', {}, signal),
  });
}

export function useStartWorkload() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<Workload>('/api/v1/workloads', body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['workloads'] });
    },
  });
}

export function useAgentCapabilities() {
  return useQuery({
    queryKey: ['agent-capabilities'],
    queryFn: ({ signal }) => api.get<AgentCapabilities>('/api/v1/agent/capabilities', {}, signal),
  });
}

export function useAgentChat() {
  const { dataSource, range } = useScope();
  return useMutation({
    mutationFn: (message: string) =>
      api.post<AgentChatResponse>(
        '/api/v1/agent/chat',
        { message, range, history: [] },
        { source: dataSource },
      ),
  });
}

export function useAuthConfig() {
  return useQuery({
    queryKey: ['auth-config'],
    queryFn: ({ signal }) => api.get<AuthConfig>('/api/v1/auth/config', {}, signal),
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useCurrentUser(enabled: boolean) {
  return useQuery({
    queryKey: ['current-user'],
    queryFn: ({ signal }) => api.get<CurrentUser>('/api/v1/auth/me', {}, signal),
    enabled,
    retry: false,
  });
}
