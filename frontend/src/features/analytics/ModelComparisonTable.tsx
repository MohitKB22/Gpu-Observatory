import type { ModelComparisonRow } from '@/api/types';
import { DemoBadge, ProviderBadge } from '@/components/ui/Badge';
import { DataTable, Td, Th } from '@/components/ui/Table';
import {
  formatLatency,
  formatNumber,
  formatPercent,
  formatRequestRate,
  formatTokensPerSecond,
} from '@/lib/format';

export function ModelComparisonTable({ rows }: { rows: ModelComparisonRow[] }) {
  return (
    <DataTable label="Model comparison">
      <thead>
        <tr>
          <Th>Model</Th>
          <Th align="right">Requests</Th>
          <Th align="right">Rate</Th>
          <Th align="right">P50</Th>
          <Th align="right">P95</Th>
          <Th align="right">P99</Th>
          <Th align="right" title="Mean completion tokens per second per request">
            Gen. speed
          </Th>
          <Th align="right">Errors</Th>
          <Th align="right" title="Share of successful requests with provider-reported token counts">
            Exact tokens
          </Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={`${row.model_id ?? 'deleted'}-${row.model_name}`} className="transition-colors hover:bg-elevated/40">
            <Td>
              <div className="flex items-center gap-2 text-xs font-medium whitespace-nowrap">
                {row.model_name}
                {row.is_demo && <DemoBadge />}
                {row.model_id === null && <span className="text-muted">(deleted)</span>}
              </div>
              <div className="mt-1">
                <ProviderBadge provider={row.provider} />
              </div>
            </Td>
            <Td align="right" numeric>
              {formatNumber(row.stats.total_requests)}
            </Td>
            <Td align="right" numeric>
              {formatRequestRate(row.stats.requests_per_second)}
            </Td>
            <Td align="right" numeric>
              {formatLatency(row.stats.latency.p50_ms)}
            </Td>
            <Td align="right" numeric>
              {formatLatency(row.stats.latency.p95_ms)}
            </Td>
            <Td align="right" numeric>
              {formatLatency(row.stats.latency.p99_ms)}
            </Td>
            <Td align="right" numeric>
              {formatTokensPerSecond(row.stats.avg_tokens_per_second)}
            </Td>
            <Td align="right" numeric className={row.stats.error_rate ? 'text-red-300' : undefined}>
              {formatPercent(row.stats.error_rate)}
            </Td>
            <Td align="right" numeric>
              {formatPercent(row.stats.exact_token_share, 0)}
            </Td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}
