import { Cpu, Database, HardDrive, MemoryStick, Workflow } from 'lucide-react';

import { getInfrastructure, getUsageHistory } from '@/api/endpoints';
import type { InfrastructureResponse, UsageSample } from '@/api/types';
import { UsageChart } from '@/components/charts/UsageChart';
import { PageHeader } from '@/components/layout/PageHeader';
import { Card, CardHeader } from '@/components/ui/Card';
import { RefreshControl } from '@/components/ui/Controls';
import { ErrorState, Skeleton, Spinner } from '@/components/ui/States';
import { useApiQuery } from '@/hooks/useApiQuery';
import { formatBytes, formatDecimal, formatDuration, formatLatency, formatPercentValue } from '@/lib/format';
import { EndpointHealthTable } from './EndpointHealthTable';
import { GpuSection } from './GpuSection';
import { InferenceServersCard } from './InferenceServersCard';
import { ResourceCard } from './ResourceCard';

const REFRESH_MS = 5000;

export default function InfrastructurePage() {
  const snapshot = useApiQuery(getInfrastructure, [], { refreshIntervalMs: REFRESH_MS });
  const history = useApiQuery(getUsageHistory, [], { refreshIntervalMs: REFRESH_MS });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Infrastructure"
        description="Resources visible to the Observatory backend, GPU telemetry where a driver is present, and live vLLM server load."
        actions={
          <RefreshControl
            updatedAt={snapshot.updatedAt}
            isFetching={snapshot.isFetching}
            onRefresh={() => {
              snapshot.refetch();
              history.refetch();
            }}
          />
        }
      />

      {snapshot.error && !snapshot.data ? (
        <ErrorState error={snapshot.error} onRetry={snapshot.refetch} />
      ) : !snapshot.data ? (
        <div className="space-y-4" aria-busy="true" aria-label="Loading infrastructure">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }, (_, index) => (
              <Skeleton key={index} className="h-36" />
            ))}
          </div>
          <Skeleton className="h-64" />
        </div>
      ) : (
        <InfrastructureContent data={snapshot.data} history={history.data?.samples} />
      )}
    </div>
  );
}

function InfrastructureContent({ data, history }: { data: InfrastructureResponse; history: UsageSample[] | undefined }) {
  const { host, worker, database } = data;
  return (
    <>
      <section aria-labelledby="host-heading" className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="host-heading" className="text-sm font-semibold">
            Backend host
          </h2>
          <p className="text-xs text-muted">Read with psutil from inside the backend process (or container).</p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <ResourceCard
            icon={<Cpu className="size-4" />}
            label="CPU"
            value={formatPercentValue(host.cpu_percent, 1)}
            percent={host.cpu_percent}
            details={[
              `${host.cpu_count} logical cores`,
              host.load_average ? `Load ${host.load_average.map((value) => formatDecimal(value, 2)).join(' · ')}` : 'Load average unavailable',
            ]}
          />
          <ResourceCard
            icon={<MemoryStick className="size-4" />}
            label="Memory"
            value={formatPercentValue(host.memory_percent, 1)}
            percent={host.memory_percent}
            details={[`${formatBytes(host.memory_used_bytes)} of ${formatBytes(host.memory_total_bytes)} in use`]}
          />
          <ResourceCard
            icon={<HardDrive className="size-4" />}
            label="Disk (/)"
            value={formatPercentValue(host.disk_percent, 1)}
            percent={host.disk_percent}
            details={[`${formatBytes(host.disk_used_bytes)} of ${formatBytes(host.disk_total_bytes)} used`]}
          />
          <ResourceCard
            icon={<Workflow className="size-4" />}
            label="API worker"
            value={`PID ${worker.pid}`}
            details={[
              `Up ${formatDuration(worker.uptime_seconds)} · ${worker.threads} threads`,
              `${formatBytes(worker.memory_rss_bytes)} RSS · ${formatPercentValue(worker.cpu_percent, 1)} CPU`,
              `${worker.configured_workers} configured worker${worker.configured_workers === 1 ? '' : 's'} · Python ${worker.python_version}`,
            ]}
          />
        </div>
        <Card>
          <CardHeader
            title="Utilisation history"
            description="Sampled every few seconds by this worker since it started (kept in memory, up to one hour)."
          />
          <div className="px-2 pb-3">
            {history && history.length > 1 ? (
              <UsageChart samples={history} showGpu={data.gpu.available} />
            ) : (
              <div className="flex h-56 items-center justify-center">
                <Spinner label="Collecting samples" />
              </div>
            )}
          </div>
        </Card>
      </section>

      <GpuSection gpu={data.gpu} />

      <InferenceServersCard servers={data.inference_servers} />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader title="Database" description="PostgreSQL connection used for persistence" />
          <dl className="space-y-3 px-4 pb-4 text-xs">
            <div className="flex items-center justify-between gap-3">
              <dt className="flex items-center gap-2 text-muted">
                <Database className="size-4" aria-hidden />
                Status
              </dt>
              <dd className={database.ok ? 'font-medium text-green-300' : 'font-medium text-red-300'}>
                {database.ok ? 'Connected' : `Unreachable${database.error ? ` (${database.error})` : ''}`}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Query round trip</dt>
              <dd className="font-mono tabular-nums">{formatLatency(database.latency_ms)}</dd>
            </div>
            <div className="space-y-1">
              <dt className="text-muted">Server version</dt>
              <dd className="font-mono break-words">{database.server_version ?? '—'}</dd>
            </div>
          </dl>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader title="Inference endpoints" description="Latest connection check for each registered model" />
          <EndpointHealthTable endpoints={data.endpoints} />
        </Card>
      </div>
    </>
  );
}
