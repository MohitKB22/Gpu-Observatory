'use client';

import { useState } from 'react';
import { PageShell } from '@/components/shell/PageShell';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge, SeverityBadge } from '@/components/ui/Badge';
import { Table, TD, TH, THead, TR } from '@/components/ui/Table';
import { EmptyState, ErrorState, LoadingState } from '@/components/states/States';
import {
  useAcknowledgeAlert,
  useAlertRules,
  useAlertSummary,
  useAlerts,
  useResolveAlert,
} from '@/hooks/useQueries';
import { EMPTY, dateTime, num, relativeTime, titleCase } from '@/lib/format';
import { cn } from '@/lib/cn';

const FILTERS = [
  { label: 'Active', value: 'active' },
  { label: 'Acknowledged', value: 'acknowledged' },
  { label: 'Resolved', value: 'resolved' },
  { label: 'All', value: '' },
];

export default function AlertsPage() {
  const [filter, setFilter] = useState('active');
  const alerts = useAlerts(filter || undefined);
  const summary = useAlertSummary();
  const rules = useAlertRules();
  const acknowledge = useAcknowledgeAlert();
  const resolve = useResolveAlert();

  const items = alerts.data?.items ?? [];

  return (
    <PageShell
      title="Alerts"
      description="Threshold alerts with an active, acknowledged and resolved lifecycle."
    >
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        {[
          { label: 'Active', value: summary.data?.active ?? 0, tone: 'text-severity-critical' },
          { label: 'Acknowledged', value: summary.data?.acknowledged ?? 0, tone: 'text-severity-medium' },
          { label: 'Resolved (24h)', value: summary.data?.resolved_24h ?? 0, tone: 'text-severity-low' },
          { label: 'Rules configured', value: rules.data?.length ?? 0, tone: 'text-ink' },
        ].map((item) => (
          <div key={item.label} className="rounded border border-line bg-surface px-3 py-2.5">
            <p className="text-2xs uppercase tracking-wide text-ink-faint">{item.label}</p>
            <p className={cn('mt-1 font-mono text-lg tabular-nums', item.tone)}>{item.value}</p>
          </div>
        ))}
      </div>

      <Card>
        <CardHeader
          title="Alerts"
          actions={
            <div className="flex gap-1">
              {FILTERS.map((option) => (
                <Button
                  key={option.value}
                  variant={filter === option.value ? 'primary' : 'ghost'}
                  onClick={() => setFilter(option.value)}
                >
                  {option.label}
                </Button>
              ))}
            </div>
          }
        />
        <CardBody className="p-0">
          {alerts.isLoading ? (
            <LoadingState rows={4} />
          ) : alerts.isError ? (
            <div className="p-4">
              <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} />
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              title={filter === 'active' ? 'No active alerts' : 'No alerts match this filter'}
              description={
                filter === 'active'
                  ? 'All configured thresholds are currently within range.'
                  : undefined
              }
            />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Severity</TH>
                  <TH>Alert</TH>
                  <TH>Entity</TH>
                  <TH align="right">Observed</TH>
                  <TH align="right">Threshold</TH>
                  <TH>Triggered</TH>
                  <TH>State</TH>
                  <TH align="right">Actions</TH>
                </TR>
              </THead>
              <tbody>
                {items.map((alert) => (
                  <TR key={alert.id}>
                    <TD><SeverityBadge severity={alert.severity} /></TD>
                    <TD>
                      <span className="block text-ink">{alert.title}</span>
                      <span className="text-2xs text-ink-faint">{titleCase(alert.condition)}</span>
                    </TD>
                    <TD>{alert.entity_label ?? EMPTY}</TD>
                    <TD align="right" mono>{num(alert.observed_value, 2)}</TD>
                    <TD align="right" mono>{num(alert.threshold, 2)}</TD>
                    <TD>
                      <span className="block">{relativeTime(alert.triggered_at)}</span>
                      <span className="text-2xs text-ink-faint">{dateTime(alert.triggered_at)}</span>
                    </TD>
                    <TD>
                      <Badge
                        variant={alert.state === 'active' ? 'default' : 'outline'}
                        className={cn(
                          alert.state === 'active' && 'border-severity-critical/40 text-severity-critical',
                          alert.state === 'acknowledged' && 'border-severity-medium/40 text-severity-medium',
                          alert.state === 'resolved' && 'border-severity-low/40 text-severity-low',
                        )}
                      >
                        {alert.state}
                      </Badge>
                      {alert.acknowledged_by ? (
                        <span className="mt-0.5 block text-2xs text-ink-faint">
                          by {alert.acknowledged_by}
                        </span>
                      ) : null}
                    </TD>
                    <TD align="right">
                      <div className="flex justify-end gap-1">
                        {alert.state === 'active' ? (
                          <Button
                            onClick={() => acknowledge.mutate({ id: alert.id })}
                            disabled={acknowledge.isPending}
                          >
                            Acknowledge
                          </Button>
                        ) : null}
                        {alert.state !== 'resolved' ? (
                          <Button onClick={() => resolve.mutate({ id: alert.id })} disabled={resolve.isPending}>
                            Resolve
                          </Button>
                        ) : null}
                      </div>
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </CardBody>
      </Card>

      {acknowledge.isError ? <ErrorState error={acknowledge.error} compact /> : null}
      {resolve.isError ? <ErrorState error={resolve.error} compact /> : null}

      <Card>
        <CardHeader title="Alert rules" description="Thresholds evaluated on each analytics cycle." />
        <CardBody className="p-0">
          {rules.isLoading ? (
            <LoadingState rows={3} />
          ) : rules.isError ? (
            <div className="p-4">
              <ErrorState error={rules.error} onRetry={() => void rules.refetch()} compact />
            </div>
          ) : !rules.data || rules.data.length === 0 ? (
            <EmptyState title="No alert rules configured" />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Rule</TH>
                  <TH>Condition</TH>
                  <TH align="right">Threshold</TH>
                  <TH>Severity</TH>
                  <TH align="right">Cooldown</TH>
                  <TH>Last fired</TH>
                  <TH align="center">Enabled</TH>
                </TR>
              </THead>
              <tbody>
                {rules.data.map((rule) => (
                  <TR key={rule.id}>
                    <TD>{rule.name}</TD>
                    <TD className="text-ink-muted">{titleCase(rule.condition)}</TD>
                    <TD align="right" mono>{num(rule.threshold, 2)}</TD>
                    <TD><SeverityBadge severity={rule.severity} /></TD>
                    <TD align="right" mono>{rule.cooldown_seconds}s</TD>
                    <TD>{rule.last_fired_at ? relativeTime(rule.last_fired_at) : 'never'}</TD>
                    <TD align="center">
                      <span className={rule.is_enabled ? 'text-nvidia' : 'text-ink-faint'}>
                        {rule.is_enabled ? 'yes' : 'no'}
                      </span>
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </CardBody>
      </Card>
    </PageShell>
  );
}
