'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { PageShell } from '@/components/shell/PageShell';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Table, TD, TH, THead, TR } from '@/components/ui/Table';
import { EmptyState, ErrorState, LoadingState } from '@/components/states/States';
import { API_BASE, fetchHealth, tokenStore } from '@/lib/api';
import { useAgentCapabilities, useAuthConfig, useCurrentUser, useDemoState } from '@/hooks/useQueries';
import { REFRESH_OPTIONS, RANGE_OPTIONS, useAppStore } from '@/stores/useAppStore';
import { Select } from '@/components/ui/Select';
import { duration, titleCase } from '@/lib/format';
import type { DataSource, HealthResponse, RangePreset } from '@/lib/types';

export default function SettingsPage() {
  const router = useRouter();
  const authConfig = useAuthConfig();
  const hasToken = typeof window !== 'undefined' && Boolean(tokenStore.access);
  const user = useCurrentUser(hasToken && authConfig.data?.auth_enabled === true);
  const capabilities = useAgentCapabilities();
  const demo = useDemoState();
  const { range, setRange, dataSource, setDataSource, refreshMs, setRefreshMs } = useAppStore();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<unknown>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((result) => setHealth(result as HealthResponse))
      .catch((cause) => setHealthError(cause));
    return () => controller.abort();
  }, []);

  function signOut() {
    tokenStore.clear();
    router.replace('/login');
  }

  return (
    <PageShell title="Settings" description="Session, connection, dashboard defaults and agent capabilities.">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Session" />
          <CardBody>
            {authConfig.data?.auth_enabled === false ? (
              <p className="text-xs text-severity-medium">
                Authentication is disabled on the backend. Every caller is treated as an
                administrator — never run a production deployment this way.
              </p>
            ) : user.isLoading ? (
              <LoadingState rows={2} />
            ) : user.data ? (
              <>
                <dl className="grid grid-cols-2 gap-y-1.5 text-xs">
                  <dt className="text-ink-faint">Email</dt>
                  <dd className="text-ink">{user.data.email}</dd>
                  <dt className="text-ink-faint">Role</dt>
                  <dd><Badge variant="accent">{user.data.role}</Badge></dd>
                  <dt className="text-ink-faint">Active</dt>
                  <dd className="text-ink">{user.data.is_active ? 'yes' : 'no'}</dd>
                </dl>
                <div className="mt-3">
                  <Button onClick={signOut}>Sign out</Button>
                </div>
              </>
            ) : (
              <EmptyState title="Not signed in" />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Backend connection" />
          <CardBody>
            {healthError ? (
              <ErrorState error={healthError} compact />
            ) : !health ? (
              <LoadingState rows={2} />
            ) : (
              <dl className="grid grid-cols-2 gap-y-1.5 text-xs">
                <dt className="text-ink-faint">API base</dt>
                <dd className="truncate font-mono text-ink">{API_BASE}</dd>
                <dt className="text-ink-faint">Status</dt>
                <dd className="text-nvidia">{health.status}</dd>
                <dt className="text-ink-faint">Version</dt>
                <dd className="text-ink">{health.version}</dd>
                <dt className="text-ink-faint">Environment</dt>
                <dd className="text-ink">{health.environment}</dd>
                <dt className="text-ink-faint">Demo Mode</dt>
                <dd className="text-ink">{health.demo_mode ? 'enabled' : 'disabled'}</dd>
                <dt className="text-ink-faint">Uptime</dt>
                <dd className="text-ink">{duration(health.uptime_seconds)}</dd>
              </dl>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Dashboard defaults" description="Applies to every screen." />
          <CardBody className="space-y-3">
            <Select
              label="Data source"
              value={dataSource}
              onValueChange={(value) => setDataSource(value as DataSource)}
              options={[
                { label: 'Demo (synthetic)', value: 'demo' },
                { label: 'Production', value: 'production' },
              ]}
            />
            <Select
              label="Time range"
              value={range}
              onValueChange={(value) => setRange(value as RangePreset)}
              options={RANGE_OPTIONS.map((option) => ({ label: option, value: option }))}
            />
            <Select
              label="Refresh interval"
              value={String(refreshMs)}
              onValueChange={(value) => setRefreshMs(Number(value))}
              options={REFRESH_OPTIONS.map((option) => ({
                label: option.label,
                value: String(option.value),
              }))}
            />
            <p className="text-2xs text-ink-faint">
              Demo and production telemetry are stored in separate namespaces and are never mixed.
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Demo Mode" />
          <CardBody>
            {demo.isLoading ? (
              <LoadingState rows={2} />
            ) : demo.data ? (
              <dl className="grid grid-cols-2 gap-y-1.5 text-xs">
                <dt className="text-ink-faint">Enabled</dt>
                <dd className="text-ink">{demo.data.enabled ? 'yes' : 'no'}</dd>
                <dt className="text-ink-faint">Scenario</dt>
                <dd className="text-ink">{titleCase(demo.data.scenario)}</dd>
                <dt className="text-ink-faint">Running</dt>
                <dd className="text-ink">{demo.data.running ? 'yes' : 'no'}</dd>
                <dt className="text-ink-faint">Simulated GPUs</dt>
                <dd className="text-ink">{demo.data.gpu_count}</dd>
              </dl>
            ) : null}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="AI agent capabilities"
          description="Every tool is read-only. The agent cannot execute commands, modify configuration or read secrets."
        />
        <CardBody className="p-0">
          {capabilities.isLoading ? (
            <LoadingState rows={4} />
          ) : capabilities.isError ? (
            <div className="p-4">
              <ErrorState error={capabilities.error} onRetry={() => void capabilities.refetch()} compact />
            </div>
          ) : capabilities.data ? (
            <>
              <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5 text-xs">
                <span className="text-ink-faint">Provider</span>
                <Badge variant={capabilities.data.llm_enabled ? 'accent' : 'default'}>
                  {capabilities.data.provider}
                </Badge>
                {capabilities.data.model ? (
                  <span className="font-mono text-2xs text-ink-muted">{capabilities.data.model}</span>
                ) : null}
                <span className="text-ink-faint">Fallback</span>
                <Badge variant="outline">{capabilities.data.fallback_engine}</Badge>
                {!capabilities.data.llm_enabled ? (
                  <span className="text-2xs text-ink-muted">
                    No language model configured — answers come entirely from the deterministic
                    diagnostics engine.
                  </span>
                ) : null}
              </div>
              <Table>
                <THead>
                  <TR>
                    <TH>Tool</TH>
                    <TH>Description</TH>
                    <TH align="center">Read-only</TH>
                  </TR>
                </THead>
                <tbody>
                  {capabilities.data.tools.map((tool) => (
                    <TR key={tool.name}>
                      <TD mono>{tool.name}</TD>
                      <TD className="text-ink-muted">{tool.description}</TD>
                      <TD align="center">
                        <span className={tool.read_only ? 'text-nvidia' : 'text-severity-critical'}>
                          {tool.read_only ? 'yes' : 'no'}
                        </span>
                      </TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            </>
          ) : null}
        </CardBody>
      </Card>
    </PageShell>
  );
}
