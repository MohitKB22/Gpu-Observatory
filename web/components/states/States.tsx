'use client';

import type { ReactNode } from 'react';
import { ApiError } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/cn';

/**
 * Loading / empty / error primitives.
 *
 * Every data surface renders one of these rather than a blank region, so the
 * user always knows whether data is arriving, absent, or failed.
 */

export function LoadingState({ label = 'Loading', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true" className="space-y-2 p-4">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="h-3 animate-pulse rounded bg-elevated"
          style={{ width: `${100 - index * 12}%` }}
        />
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 220 }: { height?: number }) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading chart"
      className="animate-pulse rounded bg-elevated/60"
      style={{ height }}
    />
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      {icon ? <div className="text-ink-faint">{icon}</div> : null}
      <p className="text-sm font-medium text-ink">{title}</p>
      {description ? <p className="max-w-md text-xs text-ink-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  compact = false,
}: {
  error: unknown;
  onRetry?: () => void;
  compact?: boolean;
}) {
  const apiError = error instanceof ApiError ? error : null;
  const message =
    apiError?.message ??
    (error instanceof Error ? error.message : 'An unexpected error occurred.');

  const hint = (() => {
    if (!apiError) return null;
    if (apiError.status === 0) {
      return 'The API did not respond. Confirm the backend is running and NEXT_PUBLIC_API_BASE_URL is correct.';
    }
    if (apiError.isAuth) return 'Your session has expired. Sign in again to continue.';
    if (apiError.isForbidden) return 'Your role does not grant access to this data.';
    if (apiError.status === 429) return 'Rate limit reached. Retry shortly.';
    return null;
  })();

  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-start gap-2 rounded border border-severity-critical/30 bg-severity-critical/5',
        compact ? 'p-3' : 'p-4',
      )}
    >
      <div className="flex items-center gap-2">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-severity-critical" />
        <p className="text-xs font-semibold text-severity-critical">
          {apiError?.code ? apiError.code.replace(/_/g, ' ') : 'Request failed'}
        </p>
      </div>
      <p className="text-xs text-ink">{message}</p>
      {hint ? <p className="text-2xs text-ink-muted">{hint}</p> : null}
      {apiError?.requestId ? (
        <p className="font-mono text-2xs text-ink-faint">request id: {apiError.requestId}</p>
      ) : null}
      {onRetry ? (
        <Button onClick={onRetry} variant="secondary">
          Retry
        </Button>
      ) : null}
    </div>
  );
}

/**
 * Renders the correct state for a query result. Keeps every screen consistent
 * and makes it impossible to forget a state.
 */
export function QueryBoundary<T>({
  isLoading,
  isError,
  error,
  data,
  onRetry,
  empty,
  isEmpty,
  loadingRows = 3,
  children,
}: {
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  data: T | undefined;
  onRetry?: () => void;
  empty?: ReactNode;
  isEmpty?: (data: T) => boolean;
  loadingRows?: number;
  children: (data: T) => ReactNode;
}) {
  if (isLoading) return <LoadingState rows={loadingRows} />;
  if (isError) return <ErrorState error={error} onRetry={onRetry} />;
  if (data === undefined) {
    return <EmptyState title="No data returned" description="The API returned an empty response." />;
  }
  if (isEmpty?.(data)) {
    return <>{empty ?? <EmptyState title="No data in this window" />}</>;
  }
  return <>{children(data)}</>;
}
