'use client';

import { PageShell } from '@/components/shell/PageShell';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Table, TD, TH, THead, TR } from '@/components/ui/Table';
import { EmptyState, ErrorState, LoadingState } from '@/components/states/States';
import { useCost, usePricing } from '@/hooks/useQueries';
import { EMPTY, int, money, num, titleCase } from '@/lib/format';

export default function CostPage() {
  const cost = useCost();
  const pricing = usePricing();
  const c = cost.data;

  return (
    <PageShell
      title="Cost Observability"
      description="Estimated inference cost derived from a configurable pricing profile."
      actions={<Badge variant="outline">all figures are estimates</Badge>}
    >
      {cost.isLoading ? (
        <LoadingState rows={4} />
      ) : cost.isError ? (
        <ErrorState error={cost.error} onRetry={() => void cost.refetch()} />
      ) : c ? (
        <>
          <Card className="border-severity-info/30">
            <CardBody>
              <p className="text-xs text-ink-muted">
                <span className="font-semibold text-severity-info">Estimate.</span> Cost is
                calculated as observed GPU-hours multiplied by the rate in the active pricing
                profile ({c.pricing_profile}: {money(c.cost_per_gpu_hour, c.currency)} per GPU-hour).
                These figures are not billing data and should not be used for invoicing.
              </p>
            </CardBody>
          </Card>

          <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-6">
            {[
              { label: 'Total cost', value: money(c.total_cost, c.currency) },
              { label: 'GPU-hours', value: num(c.gpu_hours, 3) },
              { label: 'Cost/request', value: money(c.cost_per_request, c.currency) },
              { label: 'Cost/1K tokens', value: money(c.cost_per_1k_tokens, c.currency) },
              { label: 'Cost/1M tokens', value: money(c.cost_per_1m_tokens, c.currency) },
              { label: 'Energy cost', value: c.energy_cost !== null ? money(c.energy_cost, c.currency) : EMPTY },
              { label: 'Daily (projected)', value: money(c.daily_cost, c.currency) },
              { label: 'Monthly (projected)', value: money(c.projected_monthly_cost, c.currency) },
              { label: 'Requests', value: int(c.request_count) },
              { label: 'Tokens', value: int(c.total_tokens) },
              { label: 'Rate/GPU-hour', value: money(c.cost_per_gpu_hour, c.currency) },
              { label: 'Window', value: c.range_label },
            ].map((item) => (
              <div key={item.label} className="rounded border border-line bg-surface px-3 py-2.5">
                <p className="truncate text-2xs uppercase tracking-wide text-ink-faint">{item.label}</p>
                <p className="mt-1 font-mono text-sm tabular-nums text-ink">{item.value}</p>
              </div>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader title="Cost by device" description="Attributed by observed GPU-hours." />
              <CardBody className="p-0">
                {c.breakdown.length === 0 ? (
                  <EmptyState title="No GPU telemetry in this window" />
                ) : (
                  <Table>
                    <THead>
                      <TR>
                        <TH>Device</TH>
                        <TH align="right">GPU-hours</TH>
                        <TH align="right">Cost</TH>
                        <TH align="right">Share</TH>
                      </TR>
                    </THead>
                    <tbody>
                      {c.breakdown.map((item) => (
                        <TR key={item.entity_id ?? item.label}>
                          <TD>{item.label}</TD>
                          <TD align="right" mono>{num(item.gpu_hours, 3)}</TD>
                          <TD align="right" mono>{money(item.cost, c.currency)}</TD>
                          <TD align="right" mono>{item.share_pct !== null ? `${num(item.share_pct, 1)}%` : EMPTY}</TD>
                        </TR>
                      ))}
                    </tbody>
                  </Table>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Pricing profiles"
                description="Cloud list prices vary by contract, so no rate is hardcoded."
              />
              <CardBody className="p-0">
                {pricing.isLoading ? (
                  <LoadingState rows={3} />
                ) : pricing.isError ? (
                  <div className="p-4">
                    <ErrorState error={pricing.error} onRetry={() => void pricing.refetch()} compact />
                  </div>
                ) : !pricing.data || pricing.data.length === 0 ? (
                  <EmptyState title="No pricing profiles configured" />
                ) : (
                  <Table>
                    <THead>
                      <TR>
                        <TH>Profile</TH>
                        <TH>Kind</TH>
                        <TH align="right">Per GPU-hour</TH>
                        <TH align="center">Default</TH>
                      </TR>
                    </THead>
                    <tbody>
                      {pricing.data.map((profile) => (
                        <TR key={profile.id}>
                          <TD>
                            <span className="block">{profile.name}</span>
                            {profile.provider || profile.region ? (
                              <span className="text-2xs text-ink-faint">
                                {[profile.provider, profile.region].filter(Boolean).join(' · ')}
                              </span>
                            ) : null}
                          </TD>
                          <TD>{titleCase(profile.kind)}</TD>
                          <TD align="right" mono>
                            {money(profile.cost_per_gpu_hour, profile.currency)}
                          </TD>
                          <TD align="center">
                            {profile.is_default ? <Badge variant="accent">default</Badge> : null}
                          </TD>
                        </TR>
                      ))}
                    </tbody>
                  </Table>
                )}
              </CardBody>
            </Card>
          </div>

          {c.notes.length > 0 ? (
            <Card>
              <CardHeader title="Notes" />
              <CardBody>
                <ul className="space-y-1">
                  {c.notes.map((note) => (
                    <li key={note} className="flex gap-2 text-xs text-ink-muted">
                      <span aria-hidden className="text-ink-faint">·</span>
                      <span>{note}</span>
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          ) : null}
        </>
      ) : null}
    </PageShell>
  );
}
