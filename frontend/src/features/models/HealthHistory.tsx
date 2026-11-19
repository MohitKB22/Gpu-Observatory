import { listHealthChecks } from '@/api/endpoints';
import { Spinner } from '@/components/ui/States';
import { useApiQuery } from '@/hooks/useApiQuery';
import { formatDateTime, formatLatency } from '@/lib/format';
import { cn } from '@/lib/cn';

/** Recent connection checks for one model. `revision` changes after each manual check. */
export function HealthHistory({ modelId, revision }: { modelId: string; revision: number }) {
  const query = useApiQuery((signal) => listHealthChecks(modelId, 10, signal), [modelId, revision]);

  if (query.error) return <p className="text-xs text-red-300">{query.error.message}</p>;
  if (!query.data) return <Spinner label="Loading check history" />;
  if (query.data.length === 0) {
    return <p className="text-xs text-muted">No connection checks yet. Use “Check connection” to run one.</p>;
  }

  return (
    <ol className="space-y-1.5" aria-label="Recent connection checks">
      {query.data.map((check) => {
        const healthy = check.status === 'healthy';
        return (
          <li key={check.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs">
            <span className="font-mono text-muted tabular-nums">{formatDateTime(check.checked_at)}</span>
            <span className={cn('inline-flex items-center gap-1.5 font-medium', healthy ? 'text-green-300' : 'text-red-300')}>
              <span className={cn('size-1.5 rounded-full', healthy ? 'bg-success' : 'bg-danger')} aria-hidden />
              {healthy ? 'Healthy' : 'Failed'}
            </span>
            <span className="font-mono text-muted tabular-nums">{formatLatency(check.latency_ms)}</span>
            {check.error_message && <span className="w-full text-red-200/90 sm:w-auto">{check.error_message}</span>}
          </li>
        );
      })}
    </ol>
  );
}
