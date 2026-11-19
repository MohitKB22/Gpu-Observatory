import { CheckCircle2, CircleSlash, Cpu, Database, MemoryStick, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import type { SystemHealth } from '@/api/types';
import { Card, CardHeader } from '@/components/ui/Card';
import { ProgressBar } from '@/components/ui/States';
import { formatLatency, formatPercentValue } from '@/lib/format';

export function SystemHealthCard({ system }: { system: SystemHealth }) {
  const { models } = system;
  return (
    <Card>
      <CardHeader
        title="System health"
        description="Live values from the backend host"
        actions={
          <Link to="/infrastructure" className="text-xs font-medium text-blue-300 hover:underline">
            Details
          </Link>
        }
      />
      <dl className="space-y-4 px-4 pb-4">
        <HealthRow
          icon={<Database className="size-4" />}
          label="Database"
          value={
            system.database_ok ? (
              <Ok>Connected · {formatLatency(system.database_latency_ms)}</Ok>
            ) : (
              <Failed>Unreachable</Failed>
            )
          }
        />
        <UsageRow icon={<Cpu className="size-4" />} label="CPU" value={system.cpu_percent} />
        <UsageRow icon={<MemoryStick className="size-4" />} label="Memory" value={system.memory_percent} />
        <HealthRow
          icon={<Cpu className="size-4" />}
          label="GPU"
          value={
            system.gpu_available ? (
              <span className="font-mono tabular-nums">{formatPercentValue(system.gpu_utilization_percent)} utilised</span>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-muted" title={system.gpu_unavailable_reason ?? undefined}>
                <CircleSlash className="size-3.5" aria-hidden />
                Not available
              </span>
            )
          }
        />
        <div className="border-t border-line pt-4">
          <dt className="mb-2 text-xs text-muted">Model endpoints</dt>
          <dd className="grid grid-cols-3 gap-2 text-center">
            <Count label="Healthy" value={models.healthy} tone="text-green-300" />
            <Count label="Unreachable" value={models.unhealthy} tone={models.unhealthy ? 'text-red-300' : 'text-fg'} />
            <Count label="Not checked" value={models.unknown} tone="text-muted" />
          </dd>
        </div>
      </dl>
    </Card>
  );
}

function HealthRow({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <dt className="flex items-center gap-2 text-muted">
        <span aria-hidden>{icon}</span>
        {label}
      </dt>
      <dd className="text-right">{value}</dd>
    </div>
  );
}

function UsageRow({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="space-y-1.5">
      <HealthRow icon={icon} label={label} value={<span className="font-mono tabular-nums">{formatPercentValue(value)}</span>} />
      <ProgressBar value={value} label={`${label} utilisation`} />
    </div>
  );
}

function Ok({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-green-300">
      <CheckCircle2 className="size-3.5" aria-hidden />
      {children}
    </span>
  );
}

function Failed({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-red-300">
      <XCircle className="size-3.5" aria-hidden />
      {children}
    </span>
  );
}

function Count({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg bg-elevated/60 px-2 py-2">
      <p className={`font-mono text-lg font-semibold tabular-nums ${tone}`}>{value}</p>
      <p className="text-[11px] text-muted">{label}</p>
    </div>
  );
}
