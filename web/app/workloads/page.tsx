'use client';

import { useState, type FormEvent } from 'react';
import { PageShell } from '@/components/shell/PageShell';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Table, TD, TH, THead, TR } from '@/components/ui/Table';
import { EmptyState, ErrorState, LoadingState } from '@/components/states/States';
import {
  useDemoScenarios,
  useDemoState,
  useSetDemoScenario,
  useStartWorkload,
  useWorkloadProfiles,
  useWorkloads,
} from '@/hooks/useQueries';
import { EMPTY, dateTime, duration, int, titleCase } from '@/lib/format';
import { cn } from '@/lib/cn';

export default function WorkloadsPage() {
  const demo = useDemoState();
  const scenarios = useDemoScenarios();
  const setScenario = useSetDemoScenario();
  const workloads = useWorkloads();
  const profiles = useWorkloadProfiles();
  const startWorkload = useStartWorkload();
  const [showForm, setShowForm] = useState(false);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    startWorkload.mutate(
      {
        name: String(form.get('name') ?? 'workload'),
        profile: String(form.get('profile') ?? 'low_concurrency'),
        duration_seconds: Number(form.get('duration_seconds') ?? 60),
        target_rps: Number(form.get('target_rps') ?? 5),
        concurrency: Number(form.get('concurrency') ?? 4),
      },
      { onSuccess: () => setShowForm(false) },
    );
  }

  const inputClass =
    'w-full rounded border border-line-strong bg-elevated px-2 py-1.5 text-xs text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-nvidia';

  return (
    <PageShell
      title="Workloads & Demo Mode"
      description="Drive synthetic scenarios and generate load so the diagnostics engine has something to analyse."
      actions={
        <Button variant="primary" onClick={() => setShowForm((value) => !value)}>
          {showForm ? 'Close' : 'Start workload'}
        </Button>
      }
    >
      <Card className={demo.data?.enabled ? 'border-nvidia/40' : undefined}>
        <CardHeader
          title="Demo Mode"
          description={
            demo.data?.enabled
              ? 'Synthetic telemetry is generated continuously and written to a separate namespace from production data.'
              : 'Demo Mode is disabled. Set DEMO_MODE=true to generate synthetic telemetry.'
          }
          actions={
            <Badge variant={demo.data?.enabled ? 'accent' : 'default'}>
              {demo.data?.enabled ? (demo.data.running ? 'running' : 'idle') : 'disabled'}
            </Badge>
          }
        />
        <CardBody>
          {demo.isLoading ? (
            <LoadingState rows={2} />
          ) : demo.isError ? (
            <ErrorState error={demo.error} onRetry={() => void demo.refetch()} compact />
          ) : demo.data ? (
            <>
              <dl className="mb-4 grid grid-cols-2 gap-y-1.5 text-xs sm:grid-cols-4">
                <dt className="text-ink-faint">Scenario</dt>
                <dd className="text-ink">{titleCase(demo.data.scenario)}</dd>
                <dt className="text-ink-faint">Simulated GPUs</dt>
                <dd className="text-ink">{demo.data.gpu_count}</dd>
                <dt className="text-ink-faint">Interval</dt>
                <dd className="text-ink">{demo.data.interval_seconds}s</dd>
                <dt className="text-ink-faint">Samples generated</dt>
                <dd className="text-ink">{int(demo.data.samples_generated)}</dd>
              </dl>

              {scenarios.data ? (
                <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                  {scenarios.data.map((scenario) => {
                    const isActive = demo.data?.scenario === scenario.key;
                    return (
                      <button
                        key={scenario.key}
                        type="button"
                        disabled={!demo.data?.enabled || setScenario.isPending}
                        onClick={() => setScenario.mutate(scenario.key)}
                        aria-pressed={isActive}
                        className={cn(
                          'rounded border p-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                          isActive
                            ? 'border-nvidia bg-nvidia-faint'
                            : 'border-line bg-elevated hover:border-nvidia/40',
                        )}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className={cn('text-xs font-semibold', isActive ? 'text-nvidia' : 'text-ink')}>
                            {scenario.title}
                          </p>
                          {isActive ? <Badge variant="accent">active</Badge> : null}
                        </div>
                        <p className="mt-1 text-2xs leading-relaxed text-ink-muted">
                          {scenario.description}
                        </p>
                        <p className="mt-1.5 text-2xs text-ink-faint">
                          Expected diagnosis: {titleCase(scenario.expected_diagnosis)}
                        </p>
                      </button>
                    );
                  })}
                </div>
              ) : null}

              {setScenario.isError ? (
                <div className="mt-3">
                  <ErrorState error={setScenario.error} compact />
                </div>
              ) : null}
            </>
          ) : null}
        </CardBody>
      </Card>

      {showForm ? (
        <Card>
          <CardHeader
            title="Start a synthetic workload"
            description="Requests are issued through the configured inference adapter and their real timings are recorded."
          />
          <CardBody>
            <form onSubmit={onSubmit} className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <label className="block">
                  <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Name</span>
                  <input name="name" required defaultValue="load-test" className={inputClass} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Profile</span>
                  <select name="profile" className={inputClass} defaultValue="low_concurrency">
                    {(profiles.data ?? []).map((profile) => (
                      <option key={profile.key} value={profile.key}>
                        {titleCase(profile.key)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Duration (s)</span>
                  <input name="duration_seconds" type="number" min="1" max="86400" defaultValue="30" className={inputClass} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Target req/s</span>
                  <input name="target_rps" type="number" min="1" defaultValue="5" className={inputClass} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Concurrency</span>
                  <input name="concurrency" type="number" min="1" defaultValue="4" className={inputClass} />
                </label>
              </div>
              {startWorkload.isError ? <ErrorState error={startWorkload.error} compact /> : null}
              <Button type="submit" variant="primary" disabled={startWorkload.isPending}>
                {startWorkload.isPending ? 'Starting…' : 'Start workload'}
              </Button>
            </form>

            {profiles.data ? (
              <ul className="mt-4 space-y-1 border-t border-line pt-3">
                {profiles.data.map((profile) => (
                  <li key={profile.key} className="text-2xs text-ink-muted">
                    <span className="text-ink">{titleCase(profile.key)}</span> — {profile.description}
                  </li>
                ))}
              </ul>
            ) : null}
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader title="Workload runs" description="Most recent first." />
        <CardBody className="p-0">
          {workloads.isLoading ? (
            <LoadingState rows={3} />
          ) : workloads.isError ? (
            <div className="p-4">
              <ErrorState error={workloads.error} onRetry={() => void workloads.refetch()} compact />
            </div>
          ) : !workloads.data || workloads.data.items.length === 0 ? (
            <EmptyState
              title="No workloads have been run"
              description="Start a workload to generate measurable inference traffic."
            />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Name</TH>
                  <TH>Profile</TH>
                  <TH>Status</TH>
                  <TH align="right">Requests</TH>
                  <TH align="right">Errors</TH>
                  <TH align="right">Duration</TH>
                  <TH>Started</TH>
                </TR>
              </THead>
              <tbody>
                {workloads.data.items.map((workload) => (
                  <TR key={workload.id}>
                    <TD>{workload.name}</TD>
                    <TD className="text-ink-muted">{titleCase(workload.profile)}</TD>
                    <TD>
                      <Badge
                        className={cn(
                          workload.status === 'running' && 'border-nvidia/40 text-nvidia',
                          workload.status === 'failed' && 'border-severity-critical/40 text-severity-critical',
                          workload.status === 'completed' && 'border-severity-low/40 text-severity-low',
                        )}
                      >
                        {workload.status}
                      </Badge>
                    </TD>
                    <TD align="right" mono>{int(workload.requests_generated)}</TD>
                    <TD align="right" mono>{int(workload.errors_generated)}</TD>
                    <TD align="right" mono>{duration(workload.duration_seconds)}</TD>
                    <TD>{workload.started_at ? dateTime(workload.started_at) : EMPTY}</TD>
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
