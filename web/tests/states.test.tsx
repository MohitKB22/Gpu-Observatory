import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EmptyState, ErrorState, LoadingState, QueryBoundary } from '@/components/states/States';
import { ErrorBoundary } from '@/components/states/ErrorBoundary';
import { ApiError } from '@/lib/api';
import { KpiCard } from '@/components/shell/KpiCard';
import { GpuUnavailableNotice } from '@/components/shell/GpuUnavailableNotice';

describe('state components', () => {
  it('announces loading to assistive technology', () => {
    render(<LoadingState label="Loading GPUs" />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  });

  it('renders an empty state with guidance', () => {
    render(<EmptyState title="No data" description="Widen the range." />);
    expect(screen.getByText('No data')).toBeInTheDocument();
    expect(screen.getByText('Widen the range.')).toBeInTheDocument();
  });

  it('surfaces the API message, code and request id', () => {
    render(
      <ErrorState
        error={new ApiError(503, 'database_error', 'A database error occurred.', {}, 'req-9')}
      />,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('A database error occurred.')).toBeInTheDocument();
    expect(screen.getByText(/req-9/)).toBeInTheDocument();
  });

  it('explains an unreachable backend', () => {
    render(<ErrorState error={new ApiError(0, 'network_error', 'Cannot reach the API.')} />);
    expect(screen.getByText(/backend is running/i)).toBeInTheDocument();
  });

  it('offers retry when a handler is supplied', () => {
    const onRetry = vi.fn();
    render(<ErrorState error={new Error('boom')} onRetry={onRetry} />);
    screen.getByRole('button', { name: 'Retry' }).click();
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe('QueryBoundary', () => {
  const base = { isLoading: false, isError: false, error: null, data: [1, 2, 3] };

  it('shows loading before data arrives', () => {
    render(
      <QueryBoundary {...base} isLoading data={undefined}>
        {() => <p>content</p>}
      </QueryBoundary>,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows the error state on failure', () => {
    render(
      <QueryBoundary {...base} isError error={new Error('nope')} data={undefined}>
        {() => <p>content</p>}
      </QueryBoundary>,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('shows the empty state when the predicate matches', () => {
    render(
      <QueryBoundary {...base} data={[]} isEmpty={(rows) => rows.length === 0}>
        {() => <p>content</p>}
      </QueryBoundary>,
    );
    expect(screen.getByText('No data in this window')).toBeInTheDocument();
  });

  it('renders children on success', () => {
    render(<QueryBoundary {...base}>{(rows) => <p>{rows.length} rows</p>}</QueryBoundary>);
    expect(screen.getByText('3 rows')).toBeInTheDocument();
  });
});

describe('ErrorBoundary', () => {
  it('contains a render failure instead of blanking the page', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    function Boom(): never {
      throw new Error('render exploded');
    }
    render(
      <ErrorBoundary label="Panel failed">
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Panel failed')).toBeInTheDocument();
    expect(screen.getByText('render exploded')).toBeInTheDocument();
  });
});

describe('KpiCard', () => {
  const kpi = {
    key: 'gpu_utilization',
    label: 'GPU Utilisation',
    value: 42.5,
    unit: '%',
    delta_pct: null,
    trend: null,
    is_estimate: false,
    healthy: true,
  };

  it('renders a measured value with its unit', () => {
    render(<KpiCard kpi={kpi} />);
    expect(screen.getByText('42.5')).toBeInTheDocument();
    expect(screen.getByText('%')).toBeInTheDocument();
  });

  it('renders an unmeasured value as a dash, not zero', () => {
    render(<KpiCard kpi={{ ...kpi, value: null }} />);
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('no data in window')).toBeInTheDocument();
    expect(screen.queryByText('0.0')).not.toBeInTheDocument();
  });

  it('marks estimated values', () => {
    render(<KpiCard kpi={{ ...kpi, is_estimate: true }} />);
    expect(screen.getByText('est')).toBeInTheDocument();
  });
});

describe('GpuUnavailableNotice', () => {
  const availability = {
    nvml_available: false,
    dcgm_available: false,
    gpu_count: 0,
    reason: 'nvml_init_failed',
    demo_mode: false,
    driver_version: null,
    cuda_version: null,
  };

  it('states plainly that no GPU is available and fabricates nothing', () => {
    render(<GpuUnavailableNotice availability={availability} />);
    expect(screen.getByText('NVIDIA GPU unavailable')).toBeInTheDocument();
    expect(screen.getByText(/No NVIDIA driver or GPU was detected/)).toBeInTheDocument();
    expect(screen.getByText(/none were measured/)).toBeInTheDocument();
  });

  it('renders nothing when hardware is present', () => {
    const { container } = render(
      <GpuUnavailableNotice availability={{ ...availability, nvml_available: true, gpu_count: 4 }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
