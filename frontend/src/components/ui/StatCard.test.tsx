import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StatCard } from './StatCard';

describe('StatCard', () => {
  it('shows a rising latency as a regression', () => {
    render(<StatCard label="P95" value="2.0 s" current={2000} previous={1000} polarity="lower-is-better" comparisonLabel="vs previous 24h" />);

    const delta = screen.getByText('100%');
    expect(delta).toHaveTextContent('Up');
    expect(delta.closest('span')).toHaveClass('text-red-300');
  });

  it('shows a rising throughput as an improvement', () => {
    render(<StatCard label="Speed" value="120 tok/s" current={120} previous={100} polarity="higher-is-better" />);

    expect(screen.getByText('20%').closest('span')).toHaveClass('text-green-300');
  });

  it('omits the delta when there is no previous value', () => {
    render(<StatCard label="Requests" value="10" current={10} previous={0} />);

    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });
});
