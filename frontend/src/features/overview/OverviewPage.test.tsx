import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { OverviewResponse, SummaryStats } from '@/api/types';
import { AppRoutes } from '@/App';
import { mockApi, renderWithProviders, systemInfo } from '@/test/utils';

function summary(overrides: Partial<SummaryStats> = {}): SummaryStats {
  return {
    total_requests: 120,
    error_requests: 3,
    error_rate: 0.025,
    requests_per_second: 120 / 86_400,
    latency: { p50_ms: 400, p95_ms: 1200, p99_ms: 2400 },
    avg_latency_ms: 500,
    avg_tokens_per_second: 80,
    token_throughput_per_second: 2,
    total_tokens: 10_000,
    exact_token_share: 1,
    ...overrides,
  };
}

function overview(includesDemo: boolean): OverviewResponse {
  return {
    window: '24h',
    generated_at: new Date().toISOString(),
    bucket_seconds: 900,
    scope: {
      data_source: includesDemo ? 'all' : 'real',
      demo_requests: includesDemo ? 100 : 0,
      real_requests: 20,
      includes_demo_data: includesDemo,
    },
    summary: summary(),
    previous_summary: summary({ total_requests: 80, latency: { p50_ms: 400, p95_ms: 1000, p99_ms: 2000 } }),
    timeseries: [],
    models: [],
    system: {
      database_ok: true,
      database_latency_ms: 0.8,
      cpu_percent: 12,
      memory_percent: 40,
      gpu_available: false,
      gpu_utilization_percent: null,
      gpu_unavailable_reason: 'No NVIDIA driver detected',
      models: { total: 0, enabled: 0, healthy: 0, unhealthy: 0, unknown: 0 },
    },
  };
}

describe('Overview', () => {
  it('labels demo data and drops it when switching to real data only', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/system/info': systemInfo,
      'GET /api/overview': ({ url }: { url: URL }) => overview(url.searchParams.get('data_source') !== 'real'),
    });
    renderWithProviders(<AppRoutes />);

    expect(await screen.findByText('Includes demo data.')).toBeInTheDocument();
    expect(screen.getByText('1.20 s')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument(); // requests: 120 vs 80 in the previous period

    await user.selectOptions(screen.getByLabelText('Data source'), 'real');

    await waitFor(() => expect(screen.queryByText('Includes demo data.')).not.toBeInTheDocument());
    expect(calls.at(-1)!.url.searchParams.get('data_source')).toBe('real');
    expect(window.localStorage.getItem('observatory.dataSource')).toBe('real');
  });

  it('never shows GPU numbers when telemetry is unavailable', async () => {
    mockApi({ 'GET /api/system/info': systemInfo, 'GET /api/overview': overview(false) });
    renderWithProviders(<AppRoutes />);

    expect(await screen.findByText('Not available')).toBeInTheDocument();
    expect(screen.queryByText(/utilised/)).not.toBeInTheDocument();
  });

  it('shows an error state with retry when the API is unreachable', async () => {
    const user = userEvent.setup();
    let fail = true;
    mockApi({
      'GET /api/system/info': systemInfo,
      'GET /api/overview': () => {
        if (fail) return new Response('{}', { status: 500 });
        return overview(false);
      },
    });
    renderWithProviders(<AppRoutes />);

    expect(await screen.findByText('Could not load this data')).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('System health')).toBeInTheDocument();
  });
});
