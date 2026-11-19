import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import type { UsageSample } from '@/api/types';
import { ChartTooltip } from './ChartTooltip';
import { AXIS_PROPS, CHART_COLORS, DASH, GRID_PROPS } from './chartTheme';

function clock(iso: string) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}

/** Host CPU, memory and (when present) GPU utilisation from the backend's sampler. */
export function UsageChart({ samples, showGpu }: { samples: UsageSample[]; showGpu: boolean }) {
  return (
    <div style={{ height: 220 }} role="img" aria-label="CPU, memory and GPU utilisation over time">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={samples} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis dataKey="timestamp" {...AXIS_PROPS} minTickGap={40} tickFormatter={clock} />
          <YAxis {...AXIS_PROPS} domain={[0, 100]} width={48} tickFormatter={(value: number) => `${value}%`} />
          <Tooltip
            content={(props) => (
              <ChartTooltip {...props} formatLabel={clock} formatValue={(value) => `${value.toFixed(1)}%`} />
            )}
          />
          <Legend
            iconType="plainline"
            formatter={(value: string) => <span className="text-xs text-muted">{value}</span>}
          />
          <Line dataKey="cpu_percent" name="CPU" stroke={CHART_COLORS.blue} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line
            dataKey="memory_percent"
            name="Memory"
            stroke={CHART_COLORS.violet}
            strokeWidth={2}
            strokeDasharray={DASH.dashed}
            dot={false}
            isAnimationActive={false}
          />
          {showGpu && (
            <Line
              dataKey="gpu_utilization_percent"
              name="GPU"
              stroke={CHART_COLORS.green}
              strokeWidth={2}
              strokeDasharray={DASH.dotted}
              dot={false}
              isAnimationActive={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
