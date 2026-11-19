// Types mirror the backend Pydantic schemas (backend/app/schemas). Timestamps are ISO strings.

export type DataSource = 'real' | 'demo' | 'all';
export type TimeWindow = '1h' | '6h' | '24h' | '7d';
export type ProviderKind = 'demo' | 'openai_compatible' | 'vllm' | 'huggingface';
export type ModelStatus = 'unknown' | 'healthy' | 'unhealthy';
export type RequestStatus = 'success' | 'error';
export type RequestSource = 'playground' | 'api' | 'demo_seed';
export type TokenCountSource = 'exact' | 'estimated';

export interface SystemInfo {
  version: string;
  environment: string;
  demo_mode: boolean;
  default_data_source: DataSource;
  public_demo: boolean;
  public_demo_source_url: string | null;
  max_prompt_chars: number;
  max_tokens: number;
}

export interface Model {
  id: string;
  name: string;
  provider: ProviderKind;
  model_identifier: string;
  endpoint_url: string | null;
  has_api_key: boolean;
  timeout_seconds: number;
  description: string | null;
  is_enabled: boolean;
  is_demo: boolean;
  status: ModelStatus;
  last_checked_at: string | null;
  last_check_latency_ms: number | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ModelCreatePayload {
  name: string;
  provider: ProviderKind;
  model_identifier: string;
  endpoint_url: string | null;
  api_key?: string;
  timeout_seconds: number;
  description: string | null;
  is_enabled: boolean;
}

export type ModelUpdatePayload = Partial<ModelCreatePayload> & { clear_api_key?: boolean };

export interface HealthCheck {
  id: number;
  checked_at: string;
  status: 'healthy' | 'unhealthy';
  latency_ms: number | null;
  error_kind: string | null;
  error_message: string | null;
}

export interface ConnectionCheckResult {
  check: HealthCheck;
  model: Model;
}

export interface RequestMetrics {
  latency_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  token_count_source: TokenCountSource | null;
  tokens_per_second: number | null;
}

export interface InferenceRecord {
  id: string;
  created_at: string;
  model_id: string | null;
  model_name: string;
  provider: ProviderKind;
  source: RequestSource;
  is_demo: boolean;
  status: RequestStatus;
  prompt: string;
  system_prompt: string | null;
  response_text: string | null;
  temperature: number;
  max_tokens: number;
  error_kind: string | null;
  error_message: string | null;
  upstream_status_code: number | null;
  metrics: RequestMetrics | null;
}

export interface InferencePayload {
  model_id: string;
  prompt: string;
  system_prompt: string | null;
  temperature: number;
  max_tokens: number;
  source: 'playground' | 'api';
}

export interface LogListItem {
  id: string;
  created_at: string;
  model_id: string | null;
  model_name: string;
  provider: ProviderKind;
  source: RequestSource;
  is_demo: boolean;
  status: RequestStatus;
  prompt_preview: string;
  error_kind: string | null;
  latency_ms: number | null;
  total_tokens: number | null;
  token_count_source: TokenCountSource | null;
  tokens_per_second: number | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface LatencyPercentiles {
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
}

export interface SummaryStats {
  total_requests: number;
  error_requests: number;
  error_rate: number | null;
  requests_per_second: number;
  latency: LatencyPercentiles;
  avg_latency_ms: number | null;
  avg_tokens_per_second: number | null;
  token_throughput_per_second: number;
  total_tokens: number;
  exact_token_share: number | null;
}

export interface TimeseriesPoint {
  timestamp: string;
  requests: number;
  errors: number;
  error_rate: number | null;
  requests_per_second: number;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  tokens: number;
  token_throughput_per_second: number;
  avg_tokens_per_second: number | null;
}

export interface ModelComparisonRow {
  model_id: string | null;
  model_name: string;
  provider: ProviderKind;
  is_demo: boolean;
  stats: SummaryStats;
}

export interface DataScope {
  data_source: DataSource;
  demo_requests: number;
  real_requests: number;
  includes_demo_data: boolean;
}

export interface AnalyticsResponse {
  window: TimeWindow;
  start: string;
  end: string;
  bucket_seconds: number;
  scope: DataScope;
  summary: SummaryStats;
  timeseries: TimeseriesPoint[];
  models: ModelComparisonRow[];
}

export interface OverviewModel {
  id: string;
  name: string;
  provider: ProviderKind;
  is_demo: boolean;
  is_enabled: boolean;
  status: ModelStatus;
  last_checked_at: string | null;
  requests: number;
  p95_ms: number | null;
  error_rate: number | null;
}

export interface SystemHealth {
  database_ok: boolean;
  database_latency_ms: number | null;
  cpu_percent: number;
  memory_percent: number;
  gpu_available: boolean;
  gpu_utilization_percent: number | null;
  gpu_unavailable_reason: string | null;
  models: { total: number; enabled: number; healthy: number; unhealthy: number; unknown: number };
}

export interface OverviewResponse {
  window: TimeWindow;
  generated_at: string;
  bucket_seconds: number;
  scope: DataScope;
  summary: SummaryStats;
  previous_summary: SummaryStats;
  timeseries: TimeseriesPoint[];
  models: OverviewModel[];
  system: SystemHealth;
}

export interface HostInfo {
  cpu_percent: number;
  cpu_count: number;
  load_average: [number, number, number] | null;
  memory_total_bytes: number;
  memory_used_bytes: number;
  memory_percent: number;
  disk_total_bytes: number;
  disk_used_bytes: number;
  disk_percent: number;
}

export interface WorkerInfo {
  pid: number;
  uptime_seconds: number;
  cpu_percent: number;
  memory_rss_bytes: number;
  threads: number;
  python_version: string;
  configured_workers: number;
}

export interface GpuDevice {
  index: number;
  name: string;
  utilization_percent: number | null;
  memory_used_bytes: number | null;
  memory_total_bytes: number | null;
  temperature_celsius: number | null;
  power_watts: number | null;
}

export interface GpuInfo {
  available: boolean;
  source: 'nvml' | 'nvidia-smi' | null;
  driver_version: string | null;
  devices: GpuDevice[];
  unavailable_reason: string | null;
}

export interface DatabaseHealth {
  ok: boolean;
  latency_ms: number | null;
  server_version: string | null;
  error: string | null;
}

export interface EndpointHealth {
  model_id: string;
  model_name: string;
  provider: ProviderKind;
  is_demo: boolean;
  is_enabled: boolean;
  status: ModelStatus;
  last_checked_at: string | null;
  last_check_latency_ms: number | null;
  last_error: string | null;
}

export interface InferenceServer {
  model_id: string;
  model_name: string;
  reachable: boolean;
  requests_running: number | null;
  requests_waiting: number | null;
  kv_cache_usage_percent: number | null;
  error: string | null;
}

export interface InfrastructureResponse {
  sampled_at: string;
  host: HostInfo;
  worker: WorkerInfo;
  gpu: GpuInfo;
  database: DatabaseHealth;
  endpoints: EndpointHealth[];
  inference_servers: InferenceServer[];
}

export interface UsageSample {
  timestamp: string;
  cpu_percent: number;
  memory_percent: number;
  process_cpu_percent: number;
  gpu_utilization_percent: number | null;
  gpu_memory_percent: number | null;
}

export interface UsageHistoryResponse {
  interval_seconds: number;
  samples: UsageSample[];
}
