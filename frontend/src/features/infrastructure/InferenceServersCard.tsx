import { Link } from 'react-router-dom';

import type { InferenceServer } from '@/api/types';
import { Card, CardHeader } from '@/components/ui/Card';
import { ProgressBar } from '@/components/ui/States';
import { DataTable, Td, Th } from '@/components/ui/Table';
import { formatDecimal, formatPercentValue } from '@/lib/format';

export function InferenceServersCard({ servers }: { servers: InferenceServer[] }) {
  return (
    <Card>
      <CardHeader
        title="Inference servers"
        description="Scheduler metrics scraped live from each enabled vLLM model's /metrics endpoint"
      />
      {servers.length === 0 ? (
        <p className="px-4 pb-4 text-xs text-muted">
          No enabled vLLM models. Register one in the{' '}
          <Link to="/models" className="text-blue-300 hover:underline">
            Model Registry
          </Link>{' '}
          to see running and queued requests and KV-cache usage for remote GPU servers.
        </p>
      ) : (
        <DataTable label="vLLM servers">
          <thead>
            <tr>
              <Th>Model</Th>
              <Th>Metrics endpoint</Th>
              <Th align="right">Running</Th>
              <Th align="right">Waiting</Th>
              <Th className="w-56">KV cache</Th>
            </tr>
          </thead>
          <tbody>
            {servers.map((server) => (
              <tr key={server.model_id}>
                <Td className="text-xs font-medium">{server.model_name}</Td>
                <Td className="text-xs">
                  {server.reachable ? (
                    <span className="text-green-300">Reachable</span>
                  ) : (
                    <span className="text-red-300">{server.error ?? 'Unreachable'}</span>
                  )}
                </Td>
                <Td align="right" numeric>
                  {formatDecimal(server.requests_running, 0)}
                </Td>
                <Td align="right" numeric>
                  {formatDecimal(server.requests_waiting, 0)}
                </Td>
                <Td>
                  {server.kv_cache_usage_percent === null ? (
                    <span className="text-xs text-muted">Not reported</span>
                  ) : (
                    <div className="flex items-center gap-2">
                      <ProgressBar value={server.kv_cache_usage_percent} label={`${server.model_name} KV cache usage`} />
                      <span className="w-12 text-right font-mono text-xs tabular-nums">
                        {formatPercentValue(server.kv_cache_usage_percent)}
                      </span>
                    </div>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
    </Card>
  );
}
