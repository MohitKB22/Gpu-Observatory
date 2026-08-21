'use client';

import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { PageShell } from '@/components/shell/PageShell';
import { KpiCard } from '@/components/shell/KpiCard';
import { GpuUnavailableNotice } from '@/components/shell/GpuUnavailableNotice';
import { TimeSeriesChart } from '@/components/charts/TimeSeriesChart';
import { ChartSkeleton, EmptyState, ErrorState, LoadingState } from '@/components/states/States';
import { SeverityBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  useAlerts,
  useDiagnosticsHistory,
  useGpuSeries,
  useInferenceSeries,
  useOverview,
} from '@/hooks/useQueries';
import { dateTime, num, relativeTime } from '@/lib/format';
import Link from 'next/link';

/** A chart panel that owns its own loading, error and empty states. */
function ChartPanel({
  title,
  description,
  query,
  unit,
  yDomain,
}: {
  title: string;
  description?: string;
  query: ReturnType<typeof useGpuSeries>;
  unit?: string;
  yDomain?: [number | 'auto', number | 'auto'];
}) {
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <CardBody>
        {query.isLoading ? (
          <ChartSkeleton />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} compact />
        ) : !query.data || query.data.series.length === 0 ? (
          <EmptyState
            title="No data in this window"
            description="Widen the time range, or confirm a telemetry agent is reporting."
          />
        ) : (
          <TimeSeriesChart series={query.data.series} unit={unit} yDomain={yDomain} />
        )}
      </CardBody>
    </Card>
  );
}

export default function OverviewPage() {
  const overview = useOverview();
  const gpuUtil = useGpuSeries('utilization_pct');
  const vram = useGpuSeries('memory_utilization_pct');
  const temperature = useGpuSeries('temperature_c');
  const power = useGpuSeries('power_w');
  const latency = useInferenceSeries('p50_latency_ms,p95_latency_ms,p99_latency_ms');
  const throughput = useInferenceSeries('requests_per_second');
  const tokens = useInferenceSeries('tokens_per_second');
  const alerts = useAlerts('active');
  const diagnoses = useDiagnosticsHistory();

  const latestDiagnosis = diagnoses.data?.items?.[0];
  const activeAlerts = alerts.data?.items ?? [];

  return (
    <PageShell
      title="Overview"
      description="Live operating picture for GPU, inference, batching and cost."
    >
      {overview.isError ? (
        <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />
      ) : null}

      {overview.data ? <GpuUnavailableNotice availability={overview.data.gpu_available} /> : null}

      {/* KPI row */}
      {overview.isLoading ? (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="h-[68px] animate-pulse rounded border border-line bg-surface" />
          ))}
        </div>
      ) : overview.data ? (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
          {overview.data.kpis.map((kpi) => (
            <KpiCard key={kpi.key} kpi={kpi} />
          ))}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        {/* AI diagnosis panel */}
        <Card className="xl:col-span-2">
          <CardHeader
            title="AI diagnosis"
            description="Root cause from the deterministic diagnostics engine, computed from stored telemetry."
            actions={
              <Link href="/diagnostics">
                <Button>Open diagnostics</Button>
              </Link>
            }
          />
          <CardBody>
            {diagnoses.isLoading ? (
              <LoadingState rows={4} />
            ) : diagnoses.isError ? (
              <ErrorState error={diagnoses.error} onRetry={() => void diagnoses.refetch()} compact />
            ) : !latestDiagnosis ? (
              <EmptyState
                title="No diagnosis recorded yet"
                description="Run a diagnosis to analyse the selected window."
                action={
                  <Link href="/diagnostics">
                    <Button variant="primary">Run diagnosis</Button>
                  </Link>
                }
              />
            ) : (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge severity={latestDiagnosis.severity} />
                  <p className="text-sm font-semibold text-ink">{latestDiagnosis.title}</p>
                  <span className="text-2xs text-ink-faint">
                    {relativeTime(latestDiagnosis.generated_at)} · confidence{' '}
                    {Math.round(latestDiagnosis.confidence * 100)}%
                  </span>
                </div>
                <p className="text-xs leading-relaxed text-ink-muted">
                  {latestDiagnosis.root_cause}
                </p>
                {latestDiagnosis.evidence.length > 0 ? (
                  <div>
                    <p className="mb-1 text-2xs uppercase tracking-wide text-ink-faint">Evidence</p>
                    <ul className="space-y-1">
                      {latestDiagnosis.evidence.slice(0, 4).map((item) => (
                        <li key={item} className="flex gap-2 text-xs text-ink-muted">
                          <span aria-hidden className="text-nvidia">
                            ·
                          </span>
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {latestDiagnosis.recommendations.length > 0 ? (
                  <div>
                    <p className="mb-1 text-2xs uppercase tracking-wide text-ink-faint">
                      Recommendation
                    </p>
                    <p className="text-xs text-ink">{latestDiagnosis.recommendations[0]}</p>
                  </div>
                ) : null}
              </div>
            )}
          </CardBody>
        </Card>

        {/* Active alerts */}
        <Card>
          <CardHeader
            title="Active alerts"
            description={`${overview.data?.active_alert_count ?? 0} firing`}
            actions={
              <Link href="/alerts">
                <Button>View all</Button>
              </Link>
            }
          />
          <CardBody className="p-0">
            {alerts.isLoading ? (
              <LoadingState rows={3} />
            ) : alerts.isError ? (
              <div className="p-4">
                <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} compact />
              </div>
            ) : activeAlerts.length === 0 ? (
              <EmptyState
                title="No active alerts"
                description="All configured thresholds are within range."
              />
            ) : (
              <ul className="divide-y divide-line">
                {activeAlerts.slice(0, 6).map((alert) => (
                  <li key={alert.id} className="flex items-start gap-2 px-4 py-2.5">
                    <SeverityBadge severity={alert.severity} />
                    <div className="min-w-0">
                      <p className="truncate text-xs text-ink">{alert.title}</p>
                      <p className="text-2xs text-ink-faint">
                        {alert.entity_label ?? 'system'} · {relativeTime(alert.triggered_at)}
                        {alert.observed_value !== null
                          ? ` · observed ${num(alert.observed_value, 2)}`
                          : null}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartPanel
          title="GPU utilisation"
          description="Per-device utilisation over the selected window."
          query={gpuUtil}
          unit="%"
          yDomain={[0, 100]}
        />
        <ChartPanel
          title="VRAM utilisation"
          description="Memory pressure per device."
          query={vram}
          unit="%"
          yDomain={[0, 100]}
        />
        <ChartPanel title="Latency percentiles" description="P50, P95 and P99." query={latency} unit="ms" />
        <ChartPanel title="Throughput" description="Completed requests per second." query={throughput} unit="req/s" />
        <ChartPanel title="Token throughput" description="Input plus output tokens per second." query={tokens} unit="tok/s" />
        <ChartPanel title="GPU temperature" description="Device temperature." query={temperature} unit="°C" />
        <ChartPanel title="Power draw" description="Board power per device." query={power} unit="W" />
        <Card>
          <CardHeader title="Window" description="What this dashboard is currently showing." />
          <CardBody>
            <dl className="grid grid-cols-2 gap-y-2 text-xs">
              <dt className="text-ink-faint">Data source</dt>
              <dd className="text-ink">{overview.data?.data_source ?? '—'}</dd>
              <dt className="text-ink-faint">Range</dt>
              <dd className="text-ink">{gpuUtil.data?.range_label ?? '—'}</dd>
              <dt className="text-ink-faint">Bucket</dt>
              <dd className="text-ink">
                {gpuUtil.data ? `${gpuUtil.data.bucket_seconds}s` : '—'}
              </dd>
              <dt className="text-ink-faint">Newest sample</dt>
              <dd className="text-ink">{dateTime(overview.data?.freshness.last_sample_at)}</dd>
              <dt className="text-ink-faint">Generated</dt>
              <dd className="text-ink">{dateTime(overview.data?.generated_at)}</dd>
            </dl>
          </CardBody>
        </Card>
      </div>
    </PageShell>
  );
}
