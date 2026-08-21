/** Shared response types. These mirror the backend Pydantic schemas. */

export type DataSource = 'production' | 'demo';
export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type AlertState = 'active' | 'acknowledged' | 'resolved';
export type RangePreset = '5m' | '15m' | '1h' | '6h' | '24h' | '7d';

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown>; request_id?: string };
}

export interface PageMeta {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

export interface DataFreshness {
  last_sample_at: string | null;
  age_seconds: number | null;
  is_stale: boolean;
  expected_interval_seconds: number | null;
}

export interface SeriesPoint {
  timestamp: string;
  value: number | null;
}

export interface NamedSeries {
  name: string;
  unit: string | null;
  entity_id: string | null;
  entity_label: string | null;
  points: SeriesPoint[];
}

export interface TimeSeriesResponse {
  range_label: string;
  start: string;
  end: string;
  bucket_seconds: number;
  data_source: string;
  series: NamedSeries[];
  freshness: DataFreshness;
}

export interface Gpu {
  id: string;
  uuid: string;
  index: number;
  name: string;
  host: string;
  driver_version: string | null;
  cuda_version: string | null;
  vbios_version: string | null;
  serial: string | null;
  total_memory_mb: number | null;
  power_limit_w: number | null;
  max_clock_mhz: number | null;
  max_memory_clock_mhz: number | null;
  compute_capability: string | null;
  pcie_gen: number | null;
  pcie_width: number | null;
  data_source: string;
  is_available: boolean;
  last_seen_at: string | null;
}

export interface GpuMetric {
  id: string;
  gpu_id: string;
  recorded_at: string;
  utilization_pct: number | null;
  memory_utilization_pct: number | null;
  memory_used_mb: number | null;
  memory_free_mb: number | null;
  memory_total_mb: number | null;
  temperature_c: number | null;
  power_w: number | null;
  power_limit_w: number | null;
  sm_clock_mhz: number | null;
  memory_clock_mhz: number | null;
  fan_speed_pct: number | null;
  pcie_tx_kb_s: number | null;
  pcie_rx_kb_s: number | null;
  throttle_reasons: string | null;
  ecc_errors: number | null;
}

export interface GpuProcess {
  id: string;
  pid: number;
  process_name: string | null;
  used_memory_mb: number | null;
  sm_utilization_pct: number | null;
  workload_label: string | null;
}

export interface GpuDetail {
  gpu: Gpu;
  latest: GpuMetric | null;
  processes: GpuProcess[];
  freshness: DataFreshness;
}

export interface GpuAvailability {
  nvml_available: boolean;
  dcgm_available: boolean;
  gpu_count: number;
  reason: string | null;
  demo_mode: boolean;
  driver_version: string | null;
  cuda_version: string | null;
}

export interface SystemMetric {
  id: string;
  host: string;
  recorded_at: string;
  cpu_utilization_pct: number | null;
  per_core_utilization: number[] | null;
  core_count: number | null;
  load_avg_1m: number | null;
  load_avg_5m: number | null;
  load_avg_15m: number | null;
  ram_total_mb: number | null;
  ram_used_mb: number | null;
  ram_utilization_pct: number | null;
  swap_total_mb: number | null;
  swap_used_mb: number | null;
  disk_total_gb: number | null;
  disk_used_gb: number | null;
  disk_utilization_pct: number | null;
  net_sent_kb_s: number | null;
  net_recv_kb_s: number | null;
  process_count: number | null;
}

export interface SystemSnapshot {
  latest: SystemMetric | null;
  freshness: DataFreshness;
}

export interface KpiValue {
  key: string;
  label: string;
  value: number | null;
  unit: string | null;
  delta_pct: number | null;
  trend: string | null;
  is_estimate: boolean;
  healthy: boolean | null;
}

export interface OverviewResponse {
  data_source: string;
  demo_mode: boolean;
  demo_scenario: string | null;
  kpis: KpiValue[];
  gpu_available: GpuAvailability;
  active_alert_count: number;
  latest_diagnosis_id: string | null;
  freshness: DataFreshness;
  generated_at: string;
}

export interface MLModel {
  id: string;
  name: string;
  version: string;
  display_name: string | null;
  framework: string;
  parameter_count_b: number | null;
  quantization: string;
  context_length: number | null;
  max_batch_size: number | null;
  preferred_batch_sizes: string | null;
  description: string | null;
  tags: string | null;
  is_active: boolean;
  data_source: string;
  created_at: string;
}

export interface Deployment {
  id: string;
  model_id: string;
  name: string;
  environment: string;
  gpu_id: string | null;
  gpu_count: number;
  backend: string;
  replicas: number;
  max_batch_size: number | null;
  batch_window_ms: number | null;
  tensor_parallel_size: number | null;
  status: string;
  model_load_time_ms: number | null;
}

export interface LatencyPercentiles {
  p50: number | null;
  p90: number | null;
  p95: number | null;
  p99: number | null;
  avg: number | null;
  min: number | null;
  max: number | null;
}

export interface LatencyBreakdown {
  queue_ms: number | null;
  preprocess_ms: number | null;
  execution_ms: number | null;
  postprocess_ms: number | null;
}

export interface LatencyBucket {
  lower_ms: number;
  upper_ms: number | null;
  count: number;
}

export interface InferenceSummary {
  data_source: string;
  range_label: string;
  start: string;
  end: string;
  request_count: number;
  error_count: number;
  error_rate: number | null;
  requests_per_second: number | null;
  latency: LatencyPercentiles;
  breakdown: LatencyBreakdown;
  tokens_per_second: number | null;
  input_tokens_per_second: number | null;
  output_tokens_per_second: number | null;
  total_input_tokens: number;
  total_output_tokens: number;
  avg_batch_size: number | null;
  max_batch_size: number | null;
  batch_efficiency: number | null;
  avg_concurrency: number | null;
  freshness: DataFreshness;
}

export interface InferenceRequestRow {
  id: string;
  deployment_id: string | null;
  model_id: string | null;
  started_at: string;
  total_latency_ms: number;
  queue_latency_ms: number | null;
  execution_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  batch_size: number | null;
  concurrency: number | null;
  status_code: number;
  is_error: boolean;
  error_type: string | null;
  trace_id: string | null;
}

export interface BatchMetricRow {
  id: string;
  bucket_start: string;
  avg_batch_size: number | null;
  max_batch_size: number | null;
  configured_max_batch_size: number | null;
  queue_depth: number | null;
  batch_formation_ms: number | null;
  batch_efficiency: number | null;
  gpu_utilization_pct: number | null;
  throughput_rps: number | null;
}

export interface BatchAnalysis {
  data_source: string;
  avg_batch_size: number | null;
  max_batch_size: number | null;
  configured_max_batch_size: number | null;
  batch_efficiency: number | null;
  avg_queue_depth: number | null;
  avg_batch_formation_ms: number | null;
  avg_gpu_utilization: number | null;
  throughput_rps: number | null;
  under_batching_detected: boolean;
  over_batching_detected: boolean;
  headroom_pct: number | null;
  buckets: BatchMetricRow[];
}

export interface ModelPerformance {
  model_id: string;
  model_name: string;
  version: string;
  quantization: string | null;
  framework: string | null;
  request_count: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  p99_latency_ms: number | null;
  throughput_rps: number | null;
  tokens_per_second: number | null;
  avg_batch_size: number | null;
  batch_efficiency: number | null;
  error_rate: number | null;
  avg_gpu_utilization: number | null;
  avg_vram_used_mb: number | null;
  cost_per_request: number | null;
  cost_per_1m_tokens: number | null;
  has_data: boolean;
}

export interface ComparisonDelta {
  metric: string;
  label: string;
  baseline_value: number | null;
  candidate_value: number | null;
  delta_pct: number | null;
  better: string | null;
  unit: string | null;
  lower_is_better: boolean;
}

export interface ComparisonResponse {
  data_source: string;
  range_label: string;
  models: ModelPerformance[];
  deltas: ComparisonDelta[];
  recommendation: string | null;
  recommended_model_id: string | null;
  confidence: number | null;
  caveats: string[];
  generated_at: string;
}

export interface Anomaly {
  id: string;
  detected_at: string;
  metric_kind: string;
  method: string;
  severity: Severity;
  entity_type: string | null;
  entity_label: string | null;
  observed_value: number;
  expected_value: number | null;
  deviation: number | null;
  score: number | null;
  threshold: number | null;
  sample_count: number | null;
  description: string | null;
}

export interface Alert {
  id: string;
  rule_id: string | null;
  title: string;
  condition: string;
  severity: Severity;
  state: AlertState;
  entity_type: string | null;
  entity_label: string | null;
  observed_value: number | null;
  threshold: number | null;
  message: string | null;
  triggered_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  acknowledge_note: string | null;
  resolved_at: string | null;
  resolve_reason: string | null;
}

export interface AlertSummary {
  active: number;
  acknowledged: number;
  resolved_24h: number;
  by_severity: Record<string, number>;
}

export interface AlertRule {
  id: string;
  name: string;
  condition: string;
  threshold: number;
  severity: Severity;
  for_seconds: number;
  cooldown_seconds: number;
  is_enabled: boolean;
  description: string | null;
  last_fired_at: string | null;
}

export interface Diagnosis {
  id: string | null;
  title: string;
  severity: Severity;
  kind: string;
  root_cause: string;
  evidence: string[];
  metrics: Record<string, number | string | null>;
  impact: string | null;
  recommendations: string[];
  confidence: number;
  engine: string;
  entity_type: string | null;
  entity_label: string | null;
  narrative: string | null;
  data_source: string;
  window_seconds: number | null;
  generated_at: string;
}

export interface DiagnosisReport {
  findings: Diagnosis[];
  analysed_window: string;
  data_source: string;
  engine: string;
  generated_at: string;
}

export interface CostBreakdownItem {
  label: string;
  entity_id: string | null;
  gpu_hours: number | null;
  cost: number;
  share_pct: number | null;
}

export interface CostSummary {
  data_source: string;
  currency: string;
  range_label: string;
  pricing_profile: string;
  cost_per_gpu_hour: number;
  is_estimate: boolean;
  gpu_hours: number;
  total_cost: number;
  energy_cost: number | null;
  request_count: number;
  total_tokens: number;
  cost_per_request: number | null;
  cost_per_1k_tokens: number | null;
  cost_per_1m_tokens: number | null;
  daily_cost: number | null;
  projected_monthly_cost: number | null;
  breakdown: CostBreakdownItem[];
  notes: string[];
}

export interface PricingProfile {
  id: string;
  name: string;
  kind: string;
  gpu_model: string | null;
  provider: string | null;
  region: string | null;
  cost_per_gpu_hour: number;
  currency: string;
  energy_cost_per_kwh: number | null;
  is_default: boolean;
  is_estimate: boolean;
  notes: string | null;
}

export interface DemoState {
  enabled: boolean;
  scenario: string;
  available_scenarios: string[];
  gpu_count: number;
  interval_seconds: number;
  running: boolean;
  samples_generated: number;
  started_at: string | null;
  description: string | null;
}

export interface DemoScenarioInfo {
  key: string;
  title: string;
  description: string;
  expected_diagnosis: string;
}

export interface Workload {
  id: string;
  name: string;
  profile: string;
  status: string;
  target_rps: number | null;
  concurrency: number | null;
  batch_size: number | null;
  duration_seconds: number | null;
  started_at: string | null;
  finished_at: string | null;
  requests_generated: number;
  errors_generated: number;
  error_message: string | null;
  created_at: string;
}

export interface WorkloadProfileInfo {
  key: string;
  description: string;
}

export interface ToolCallRecord {
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  duration_ms: number | null;
  summary: string | null;
  error: string | null;
}

export interface AgentChatResponse {
  answer: string;
  engine: string;
  tool_calls: ToolCallRecord[];
  citations: string[];
  confidence: number;
  data_source: string;
  refused: boolean;
  refusal_reason: string | null;
  generated_at: string;
}

export interface AgentToolInfo {
  name: string;
  description: string;
  read_only: boolean;
}

export interface AgentCapabilities {
  llm_enabled: boolean;
  provider: string;
  model: string | null;
  tools: AgentToolInfo[];
  max_tool_iterations: number;
  fallback_engine: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  environment: string;
  demo_mode: boolean;
  uptime_seconds: number;
  timestamp: string;
}

export interface AuthConfig {
  auth_enabled: boolean;
  access_token_lifetime_seconds: number;
  api_key_prefix: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  last_login_at: string | null;
}
