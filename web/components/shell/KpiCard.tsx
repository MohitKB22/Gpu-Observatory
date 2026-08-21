import { cn } from '@/lib/cn';
import { EMPTY, num } from '@/lib/format';
import type { KpiValue } from '@/lib/types';

/**
 * A single KPI. A null value renders as an em dash, never as zero, so an
 * unmeasured metric is visually distinct from a measured zero.
 */
export function KpiCard({ kpi }: { kpi: KpiValue }) {
  const hasValue = kpi.value !== null && kpi.value !== undefined;
  const digits = kpi.unit === 'req/s' ? 2 : kpi.value !== null && Math.abs(kpi.value) < 1 ? 4 : 1;

  return (
    <div
      className={cn(
        'rounded border border-line bg-surface px-3 py-2.5',
        kpi.healthy === false && 'border-severity-medium/40',
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <p className="truncate text-2xs uppercase tracking-wide text-ink-faint">{kpi.label}</p>
        {kpi.is_estimate ? (
          <span
            title="Derived from the configured pricing profile, not billing data"
            className="shrink-0 rounded border border-line-strong px-1 text-[9px] uppercase tracking-wide text-ink-faint"
          >
            est
          </span>
        ) : null}
      </div>
      <p
        className={cn(
          'mt-1 font-mono text-lg tabular-nums',
          hasValue ? 'text-ink' : 'text-ink-faint',
          kpi.healthy === false && 'text-severity-medium',
        )}
      >
        {hasValue ? num(kpi.value, digits) : EMPTY}
        {hasValue && kpi.unit ? (
          <span className="ml-1 text-xs text-ink-muted">{kpi.unit}</span>
        ) : null}
      </p>
      {!hasValue ? <p className="mt-0.5 text-2xs text-ink-faint">no data in window</p> : null}
    </div>
  );
}
