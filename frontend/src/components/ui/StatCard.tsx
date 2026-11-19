import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

/** Which direction is an improvement, so the delta can be coloured as good or bad. */
export type DeltaPolarity = 'higher-is-better' | 'lower-is-better' | 'neutral';

interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  current?: number | null;
  previous?: number | null;
  polarity?: DeltaPolarity;
  comparisonLabel?: string;
  /** "compact" for rows of six cards, where long values like "0.67 req/min" must still fit. */
  size?: 'default' | 'compact';
  className?: string;
}

export function StatCard({
  label,
  value,
  hint,
  icon,
  current,
  previous,
  polarity = 'neutral',
  comparisonLabel,
  size = 'default',
  className,
}: StatCardProps) {
  return (
    <div className={cn('rounded-xl border border-line bg-card p-4', className)}>
      <div className="flex items-center justify-between gap-2 text-xs font-medium text-muted">
        <span>{label}</span>
        {icon && <span aria-hidden>{icon}</span>}
      </div>
      <div
        className={cn(
          'mt-2 font-mono font-semibold tracking-tight whitespace-nowrap text-fg tabular-nums',
          size === 'compact' ? 'text-xl' : 'text-2xl',
        )}
      >
        {value}
      </div>
      <div className="mt-1.5 flex min-h-5 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
        <Delta current={current} previous={previous} polarity={polarity} comparisonLabel={comparisonLabel} />
        {hint && <span>{hint}</span>}
      </div>
    </div>
  );
}

function Delta({
  current,
  previous,
  polarity,
  comparisonLabel,
}: Pick<StatCardProps, 'current' | 'previous' | 'polarity' | 'comparisonLabel'>) {
  if (current === null || current === undefined || previous === null || previous === undefined || previous === 0) {
    return null;
  }
  const change = (current - previous) / Math.abs(previous);
  if (!Number.isFinite(change) || Math.abs(change) < 0.005) {
    return <span>No change{comparisonLabel ? ` ${comparisonLabel}` : ''}</span>;
  }

  const rising = change > 0;
  const good = polarity === 'neutral' ? null : rising === (polarity === 'higher-is-better');
  const Arrow = rising ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-0.5 font-medium tabular-nums',
        good === null ? 'text-blue-300' : good ? 'text-green-300' : 'text-red-300',
      )}
    >
      <Arrow className="size-3.5" aria-hidden />
      <span className="sr-only">{rising ? 'Up' : 'Down'}</span>
      {Math.abs(change * 100).toFixed(Math.abs(change) < 0.1 ? 1 : 0)}%
      {comparisonLabel && <span className="font-normal text-muted"> {comparisonLabel}</span>}
    </span>
  );
}
