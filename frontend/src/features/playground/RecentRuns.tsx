import { Link } from 'react-router-dom';

import type { LogListItem, Page } from '@/api/types';
import { DemoBadge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/States';
import { RequestStatusBadge } from '@/components/ui/StatusIndicator';
import { DataTable, Td, Th } from '@/components/ui/Table';
import type { QueryResult } from '@/hooks/useApiQuery';
import { useNow } from '@/hooks/useNow';
import { formatLatency, formatRelativeTime, formatTokens } from '@/lib/format';

export function RecentRuns({ query }: { query: QueryResult<Page<LogListItem>> }) {
  const now = useNow(10_000);
  const runs = query.data?.items ?? [];

  return (
    <Card>
      <CardHeader
        title="Recent playground runs"
        actions={
          <Link to="/logs?source=playground" className="text-xs font-medium text-blue-300 hover:underline">
            View all
          </Link>
        }
      />
      {query.error ? (
        <p className="px-4 pb-4 text-xs text-red-300">{query.error.message}</p>
      ) : !query.data ? (
        <div className="px-4 pb-4">
          <Spinner />
        </div>
      ) : runs.length === 0 ? (
        <p className="px-4 pb-4 text-xs text-muted">No playground runs yet.</p>
      ) : (
        <DataTable label="Recent playground runs">
          <thead>
            <tr>
              <Th>When</Th>
              <Th>Model</Th>
              <Th>Status</Th>
              <Th>Prompt</Th>
              <Th align="right">Latency</Th>
              <Th align="right">Tokens</Th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="transition-colors hover:bg-elevated/40">
                <Td className="text-xs whitespace-nowrap text-muted">
                  <Link to={`/logs?request=${run.id}`} className="hover:text-fg hover:underline">
                    {formatRelativeTime(run.created_at, now)}
                  </Link>
                </Td>
                <Td>
                  <span className="flex items-center gap-2 text-xs font-medium">
                    {run.model_name}
                    {run.is_demo && <DemoBadge />}
                  </span>
                </Td>
                <Td>
                  <RequestStatusBadge status={run.status} />
                </Td>
                <Td className="max-w-80">
                  <span className="block truncate text-xs text-muted">{run.prompt_preview}</span>
                </Td>
                <Td align="right" numeric>
                  {formatLatency(run.latency_ms)}
                </Td>
                <Td align="right" numeric>
                  {formatTokens(run.total_tokens, run.token_count_source)}
                </Td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
    </Card>
  );
}
