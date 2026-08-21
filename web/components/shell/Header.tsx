'use client';

import { useEffect, useState } from 'react';
import { Select } from '@/components/ui/Select';
import { Badge } from '@/components/ui/Badge';
import { REFRESH_OPTIONS, RANGE_OPTIONS, useAppStore } from '@/stores/useAppStore';
import { useDemoState, useOverview } from '@/hooks/useQueries';
import { fetchHealth } from '@/lib/api';
import { relativeTime, titleCase } from '@/lib/format';
import { cn } from '@/lib/cn';
import type { DataSource, RangePreset } from '@/lib/types';
import type { HealthResponse } from '@/lib/types';

/** Connection state derived from the health endpoint, polled independently. */
function useBackendHealth() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    const probe = async () => {
      try {
        const result = (await fetchHealth(controller.signal)) as HealthResponse;
        if (!cancelled) {
          setHealth(result);
          setOnline(true);
        }
      } catch {
        if (!cancelled) setOnline(false);
      }
    };

    void probe();
    const timer = setInterval(() => void probe(), 15_000);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(timer);
    };
  }, []);

  return { health, online };
}

export function Header() {
  const { range, setRange, dataSource, setDataSource, refreshMs, setRefreshMs } = useAppStore();
  const { health, online } = useBackendHealth();
  const { data: overview } = useOverview();
  const { data: demo } = useDemoState();

  const freshness = overview?.freshness;
  const isDemo = dataSource === 'demo';

  return (
    <header className="border-b border-line bg-surface">
      {isDemo ? (
        <div
          role="status"
          className="flex items-center gap-2 border-b border-nvidia/30 bg-nvidia-faint px-4 py-1.5"
        >
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-nvidia" />
          <p className="text-2xs font-semibold uppercase tracking-wide text-nvidia">
            Demo Mode — synthetic telemetry
          </p>
          <p className="truncate text-2xs text-ink-muted">
            {demo?.scenario ? `Scenario: ${titleCase(demo.scenario)}.` : null} This data is
            generated for demonstration and is never mixed with production telemetry.
          </p>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-3">
          <h1 className="truncate text-sm font-semibold tracking-tight text-ink">
            NVIDIA AI Performance Observatory
          </h1>
          <Badge variant={isDemo ? 'accent' : 'outline'}>{isDemo ? 'Demo' : 'Production'}</Badge>
          {health?.environment ? <Badge variant="outline">{health.environment}</Badge> : null}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Select
            label="Source"
            value={dataSource}
            onValueChange={(value) => setDataSource(value as DataSource)}
            options={[
              { label: 'Demo', value: 'demo' },
              { label: 'Production', value: 'production' },
            ]}
          />
          <Select
            label="Range"
            value={range}
            onValueChange={(value) => setRange(value as RangePreset)}
            options={RANGE_OPTIONS.map((option) => ({ label: option, value: option }))}
          />
          <Select
            label="Refresh"
            value={String(refreshMs)}
            onValueChange={(value) => setRefreshMs(Number(value))}
            options={REFRESH_OPTIONS.map((option) => ({
              label: option.label,
              value: String(option.value),
            }))}
          />

          <div className="flex items-center gap-1.5 text-2xs">
            <span
              aria-hidden
              className={cn(
                'h-1.5 w-1.5 rounded-full',
                online === null && 'bg-ink-faint',
                online === true && 'bg-nvidia',
                online === false && 'bg-severity-critical',
              )}
            />
            <span className="text-ink-muted">
              {online === null ? 'Connecting' : online ? 'Connected' : 'Backend unreachable'}
            </span>
          </div>

          <div className="text-2xs text-ink-faint" title="Age of the newest telemetry sample">
            {freshness?.last_sample_at ? (
              <span className={cn(freshness.is_stale && 'text-severity-medium')}>
                {freshness.is_stale ? 'Stale · ' : 'Updated '}
                {relativeTime(freshness.last_sample_at)}
              </span>
            ) : (
              <span>No samples</span>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
