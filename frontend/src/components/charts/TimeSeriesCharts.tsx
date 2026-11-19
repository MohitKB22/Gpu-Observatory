import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { TimeseriesPoint } from '@/api/types';
import { formatBucketTime, formatCompact, formatLatency, formatNumber } from '@/lib/format';
import { ChartTooltip } from './ChartTooltip';
import { AXIS_PROPS, CHART_COLORS, CHART_HEIGHT, DASH, GRID_PROPS } from './chartTheme';

interface SeriesChartProps {
  points: TimeseriesPoint[];
  bucketSeconds: number;
  height?: number;
}

function legendFormatter(value: string) {
  return <span className="text-xs text-muted">{value}</span>;
}

function xAxis(bucketSeconds: number) {
  return (
    <XAxis
      dataKey="timestamp"
      {...AXIS_PROPS}
      minTickGap={32}
      tickFormatter={(value: string) => formatBucketTime(value, bucketSeconds)}
    />
  );
}

/** Request volume (successes and errors stacked) with P95 latency on a second axis. */
export function TrafficChart({ points, bucketSeconds, height = CHART_HEIGHT }: SeriesChartProps) {
  const data = points.map((point) => ({ ...point, succeeded: point.requests - point.errors }));
  return (
    <div style={{ height }} role="img" aria-label="Requests per interval and P95 latency over time">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -8 }}>
          <CartesianGrid {...GRID_PROPS} />
          {xAxis(bucketSeconds)}
          <YAxis yAxisId="requests" {...AXIS_PROPS} width={44} allowDecimals={false} tickFormatter={formatCompact} />
          <YAxis
            yAxisId="latency"
            orientation="right"
            {...AXIS_PROPS}
            width={56}
            tickFormatter={(value: number) => formatLatency(value)}
          />
          <Tooltip
            cursor={{ fill: 'rgba(148,163,184,0.08)' }}
            content={(props) => (
              <ChartTooltip
                {...props}
                formatLabel={(label) => formatBucketTime(label, bucketSeconds)}
                formatValue={(value, name) => (name === 'P95 latency' ? formatLatency(value) : formatNumber(value))}
              />
            )}
          />
          <Legend iconType="circle" iconSize={8} formatter={legendFormatter} />
          <Bar yAxisId="requests" dataKey="succeeded" name="Successful" stackId="volume" fill={CHART_COLORS.blue} fillOpacity={0.75} isAnimationActive={false} />
          <Bar yAxisId="requests" dataKey="errors" name="Errors" stackId="volume" fill={CHART_COLORS.red} radius={[2, 2, 0, 0]} isAnimationActive={false} />
          <Line
            yAxisId="latency"
            dataKey="p95_ms"
            name="P95 latency"
            stroke={CHART_COLORS.violet}
            strokeWidth={2}
            strokeDasharray={DASH.dashed}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function LatencyPercentilesChart({ points, bucketSeconds, height = CHART_HEIGHT }: SeriesChartProps) {
  return (
    <div style={{ height }} role="img" aria-label="P50, P95 and P99 latency over time">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          {xAxis(bucketSeconds)}
          <YAxis {...AXIS_PROPS} width={60} tickFormatter={(value: number) => formatLatency(value)} />
          <Tooltip
            content={(props) => (
              <ChartTooltip
                {...props}
                formatLabel={(label) => formatBucketTime(label, bucketSeconds)}
                formatValue={(value) => formatLatency(value)}
              />
            )}
          />
          <Legend iconType="plainline" formatter={legendFormatter} />
          <Line dataKey="p50_ms" name="P50" stroke={CHART_COLORS.blue} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line
            dataKey="p95_ms"
            name="P95"
            stroke={CHART_COLORS.violet}
            strokeWidth={2}
            strokeDasharray={DASH.dashed}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            dataKey="p99_ms"
            name="P99"
            stroke={CHART_COLORS.amber}
            strokeWidth={2}
            strokeDasharray={DASH.dotted}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

interface MetricChartProps extends SeriesChartProps {
  dataKey: keyof TimeseriesPoint;
  name: string;
  color: string;
  format: (value: number) => string;
  variant?: 'area' | 'bar';
}

/** One metric over time, used for request rate, token throughput and error rate. */
export function MetricChart({
  points,
  bucketSeconds,
  dataKey,
  name,
  color,
  format,
  variant = 'area',
  height = 200,
}: MetricChartProps) {
  const tooltip = (
    <Tooltip
      cursor={variant === 'bar' ? { fill: 'rgba(148,163,184,0.08)' } : undefined}
      content={(props) => (
        <ChartTooltip
          {...props}
          formatLabel={(label) => formatBucketTime(label, bucketSeconds)}
          formatValue={(value) => format(value)}
        />
      )}
    />
  );
  const gradientId = `gradient-${String(dataKey)}`;
  return (
    <div style={{ height }} role="img" aria-label={`${name} over time`}>
      <ResponsiveContainer width="100%" height="100%">
        {variant === 'bar' ? (
          <BarChart data={points} margin={{ top: 8, right: 4, bottom: 0, left: -4 }}>
            <CartesianGrid {...GRID_PROPS} />
            {xAxis(bucketSeconds)}
            <YAxis {...AXIS_PROPS} width={52} tickFormatter={format} />
            {tooltip}
            <Bar dataKey={dataKey} name={name} fill={color} fillOpacity={0.8} radius={[2, 2, 0, 0]} isAnimationActive={false} />
          </BarChart>
        ) : (
          <AreaChart data={points} margin={{ top: 8, right: 4, bottom: 0, left: -4 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid {...GRID_PROPS} />
            {xAxis(bucketSeconds)}
            <YAxis {...AXIS_PROPS} width={52} tickFormatter={format} />
            {tooltip}
            <Area
              dataKey={dataKey}
              name={name}
              stroke={color}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              connectNulls
              isAnimationActive={false}
            />
          </AreaChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
