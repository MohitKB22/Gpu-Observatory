import { AlertTriangle, FlaskConical, Inbox, Loader2, RotateCw } from 'lucide-react';
import type { ReactNode } from 'react';

import type { DataScope } from '@/api/types';
import { formatNumber } from '@/lib/format';
import { cn } from '@/lib/cn';
import { Button } from './Button';

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-elevated', className)} aria-hidden />;
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      <span className="text-xs">{label}</span>
    </span>
  );
}

interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, description, icon, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-10 text-center', className)}>
      <div className="mb-3 flex size-10 items-center justify-center rounded-full border border-line bg-elevated text-muted">
        {icon ?? <Inbox className="size-5" aria-hidden />}
      </div>
      <p className="text-sm font-medium text-fg">{title}</p>
      {description && <p className="mt-1 max-w-md text-xs text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry, className }: { error: Error; onRetry?: () => void; className?: string }) {
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-xl border border-danger/30 bg-danger/5 px-6 py-8 text-center',
        className,
      )}
    >
      <AlertTriangle className="size-5 text-danger" aria-hidden />
      <div>
        <p className="text-sm font-medium text-fg">Could not load this data</p>
        <p className="mt-1 text-xs text-muted">{error.message}</p>
      </div>
      {onRetry && (
        <Button size="sm" onClick={onRetry} icon={<RotateCw className="size-3.5" aria-hidden />}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** Shown whenever simulated data contributes to the numbers on screen. */
export function DemoDataNotice({ scope }: { scope: DataScope | undefined }) {
  if (!scope?.includes_demo_data) return null;
  const total = scope.demo_requests + scope.real_requests;
  const allDemo = scope.real_requests === 0;
  return (
    <div className="flex items-start gap-3 rounded-lg border border-secondary/30 bg-secondary/10 px-3.5 py-2.5 text-xs">
      <FlaskConical className="mt-0.5 size-4 shrink-0 text-violet-300" aria-hidden />
      <p className="text-violet-100">
        <span className="font-semibold">Includes demo data.</span>{' '}
        {allDemo
          ? 'Every request in this view is simulated demo traffic, not a production measurement.'
          : `${formatNumber(scope.demo_requests)} of ${formatNumber(total)} requests in this view are simulated demo traffic.`}{' '}
        Switch the data source to <span className="font-medium">Real only</span> to exclude it.
      </p>
    </div>
  );
}

export function ProgressBar({ value, label, className }: { value: number | null; label: string; className?: string }) {
  const clamped = value === null ? 0 : Math.max(0, Math.min(100, value));
  const tone = clamped >= 90 ? 'bg-danger' : clamped >= 75 ? 'bg-warning' : 'bg-primary';
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value === null ? undefined : Math.round(clamped)}
      className={cn('h-1.5 w-full overflow-hidden rounded-full bg-elevated', className)}
    >
      <div className={cn('h-full rounded-full transition-[width] duration-300', tone)} style={{ width: `${clamped}%` }} />
    </div>
  );
}
