import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import type { ModelComparisonRow } from '@/api/types';
import { formatLatency } from '@/lib/format';
import { ChartTooltip } from './ChartTooltip';
import { AXIS_PROPS, CHART_COLORS, GRID_PROPS } from './chartTheme';

/** P95 latency per model, sorted slowest first so the outlier is at the top. */
export function ModelLatencyChart({ rows }: { rows: ModelComparisonRow[] }) {
  const data = rows
    .filter((row) => row.stats.latency.p95_ms !== null)
    .map((row) => ({ name: row.model_name, p95: row.stats.latency.p95_ms, demo: row.is_demo }))
    .sort((a, b) => (b.p95 ?? 0) - (a.p95 ?? 0));
  const height = Math.max(120, data.length * 36 + 40);

  return (
    <div style={{ height }} role="img" aria-label="P95 latency by model, slowest first">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
          <CartesianGrid {...GRID_PROPS} vertical horizontal={false} />
          <XAxis type="number" {...AXIS_PROPS} tickFormatter={(value: number) => formatLatency(value)} />
          <YAxis type="category" dataKey="name" {...AXIS_PROPS} width={130} />
          <Tooltip
            cursor={{ fill: 'rgba(148,163,184,0.08)' }}
            content={(props) => <ChartTooltip {...props} formatValue={(value) => formatLatency(value)} />}
          />
          <Bar dataKey="p95" name="P95 latency" radius={[0, 3, 3, 0]} barSize={18} isAnimationActive={false}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.demo ? CHART_COLORS.violet : CHART_COLORS.blue} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
