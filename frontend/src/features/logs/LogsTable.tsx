import type { LogListItem } from '@/api/types';
import { Badge, DemoBadge } from '@/components/ui/Badge';
import { RequestStatusBadge } from '@/components/ui/StatusIndicator';
import { DataTable, Td, Th } from '@/components/ui/Table';
import { useNow } from '@/hooks/useNow';
import { formatDateTime, formatLatency, formatRelativeTime, formatTokens, formatTokensPerSecond } from '@/lib/format';

const SOURCE_LABELS: Record<string, string> = {
  playground: 'Playground',
  api: 'API',
  demo_seed: 'Sample data',
};

export function LogsTable({ items, onSelect }: { items: LogListItem[]; onSelect: (id: string) => void }) {
  const now = useNow(15_000);
  return (
    <DataTable label="Request log">
      <thead>
        <tr>
          <Th>Time</Th>
          <Th>Model</Th>
          <Th>Status</Th>
          <Th>Prompt</Th>
          <Th align="right">Latency</Th>
          <Th align="right" title="~ marks estimated counts">
            Tokens
          </Th>
          <Th align="right">Tok/s</Th>
          <Th>Source</Th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr
            key={item.id}
            onClick={() => onSelect(item.id)}
            className="cursor-pointer transition-colors hover:bg-elevated/50"
          >
            <Td className="text-xs whitespace-nowrap">
              {/* The button is the keyboard and screen-reader entry point; the row click is a mouse shortcut. */}
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect(item.id);
                }}
                className="cursor-pointer rounded text-left text-fg hover:underline"
                title={formatDateTime(item.created_at)}
                aria-label={`View request from ${formatDateTime(item.created_at)} to ${item.model_name}`}
              >
                {formatRelativeTime(item.created_at, now)}
              </button>
            </Td>
            <Td>
              <span className="flex items-center gap-2 text-xs font-medium whitespace-nowrap">
                {item.model_name}
                {item.is_demo && <DemoBadge />}
              </span>
            </Td>
            <Td>
              <RequestStatusBadge status={item.status} />
            </Td>
            <Td className="max-w-[28rem]">
              <span className="block truncate text-xs text-muted">
                {item.error_kind && <span className="mr-1.5 text-red-300">[{item.error_kind}]</span>}
                {item.prompt_preview}
              </span>
            </Td>
            <Td align="right" numeric>
              {formatLatency(item.latency_ms)}
            </Td>
            <Td align="right" numeric title={item.token_count_source === 'estimated' ? 'Estimated' : undefined}>
              {formatTokens(item.total_tokens, item.token_count_source)}
            </Td>
            <Td align="right" numeric>
              {formatTokensPerSecond(item.tokens_per_second)}
            </Td>
            <Td>
              <Badge>{SOURCE_LABELS[item.source] ?? item.source}</Badge>
            </Td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}
