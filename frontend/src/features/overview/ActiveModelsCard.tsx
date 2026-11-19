import { Boxes } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { OverviewModel, TimeWindow } from '@/api/types';
import { DemoBadge, ProviderBadge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/States';
import { ModelStatusIndicator } from '@/components/ui/StatusIndicator';
import { DataTable, Td, Th } from '@/components/ui/Table';
import { formatLatency, formatNumber, formatPercent } from '@/lib/format';

export function ActiveModelsCard({ models, timeWindow }: { models: OverviewModel[]; timeWindow: TimeWindow }) {
  return (
    <Card>
      <CardHeader
        title="Models"
        description={`Connection status and traffic over the last ${timeWindow}`}
        actions={
          <Link to="/models" className="text-xs font-medium text-blue-300 hover:underline">
            Manage models
          </Link>
        }
      />
      {models.length === 0 ? (
        <EmptyState
          icon={<Boxes className="size-5" aria-hidden />}
          title="No models registered"
          description="Register an OpenAI-compatible, vLLM or Hugging Face endpoint to start collecting metrics."
          action={
            <Link to="/models" className="text-xs font-medium text-blue-300 hover:underline">
              Register a model
            </Link>
          }
        />
      ) : (
        <DataTable label="Registered models">
          <thead>
            <tr>
              <Th>Model</Th>
              <Th>Provider</Th>
              <Th>Status</Th>
              <Th align="right">Requests</Th>
              <Th align="right">P95</Th>
              <Th align="right">Error rate</Th>
            </tr>
          </thead>
          <tbody>
            {models.map((model) => (
              <tr key={model.id} className="transition-colors hover:bg-elevated/40">
                <Td>
                  <span className="flex items-center gap-2 font-medium whitespace-nowrap">
                    {model.name}
                    {model.is_demo && <DemoBadge />}
                  </span>
                </Td>
                <Td>
                  <ProviderBadge provider={model.provider} />
                </Td>
                <Td>
                  <ModelStatusIndicator status={model.status} enabled={model.is_enabled} />
                </Td>
                <Td align="right" numeric>
                  {formatNumber(model.requests)}
                </Td>
                <Td align="right" numeric>
                  {formatLatency(model.p95_ms)}
                </Td>
                <Td align="right" numeric>
                  {formatPercent(model.error_rate)}
                </Td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
    </Card>
  );
}
