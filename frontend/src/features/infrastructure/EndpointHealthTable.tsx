import type { EndpointHealth } from '@/api/types';
import { DemoBadge, ProviderBadge } from '@/components/ui/Badge';
import { ModelStatusIndicator } from '@/components/ui/StatusIndicator';
import { DataTable, Td, Th } from '@/components/ui/Table';
import { useNow } from '@/hooks/useNow';
import { formatLatency, formatRelativeTime } from '@/lib/format';

export function EndpointHealthTable({ endpoints }: { endpoints: EndpointHealth[] }) {
  const now = useNow(10_000);
  if (endpoints.length === 0) {
    return <p className="px-4 pb-4 text-xs text-muted">No models registered.</p>;
  }
  return (
    <DataTable label="Endpoint health">
      <thead>
        <tr>
          <Th>Model</Th>
          <Th>Provider</Th>
          <Th>Status</Th>
          <Th>Last check</Th>
          <Th align="right">Check latency</Th>
        </tr>
      </thead>
      <tbody>
        {endpoints.map((endpoint) => (
          <tr key={endpoint.model_id}>
            <Td>
              <span className="flex items-center gap-2 text-xs font-medium">
                {endpoint.model_name}
                {endpoint.is_demo && <DemoBadge />}
              </span>
              {endpoint.last_error && (
                <span className="mt-0.5 block max-w-md truncate text-[11px] text-red-200" title={endpoint.last_error}>
                  {endpoint.last_error}
                </span>
              )}
            </Td>
            <Td>
              <ProviderBadge provider={endpoint.provider} />
            </Td>
            <Td>
              <ModelStatusIndicator status={endpoint.status} enabled={endpoint.is_enabled} />
            </Td>
            <Td className="text-xs whitespace-nowrap text-muted">{formatRelativeTime(endpoint.last_checked_at, now)}</Td>
            <Td align="right" numeric>
              {formatLatency(endpoint.last_check_latency_ms)}
            </Td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}
