'use client';

import { useMemo } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { NamedSeries } from '@/lib/types';
import { timeOfDay } from '@/lib/format';

const PALETTE = ['#76b900', '#5b9dd9', '#d9a441', '#e0703c', '#9b8bd6', '#4fb286', '#e05252', '#8fd400'];

interface Props {
  series: NamedSeries[];
  height?: number;
  unit?: string | null;
  yDomain?: [number | 'auto', number | 'auto'];
  showLegend?: boolean;
}

/**
 * Multi-series line chart. Series are joined on their bucket timestamp so
 * Recharts receives one row per bucket rather than one per point.
 */
export function TimeSeriesChart({
  series,
  height = 220,
  unit,
  yDomain,
  showLegend = true,
}: Props) {
  const { rows, keys } = useMemo(() => {
    const byTimestamp = new Map<string, Record<string, number | string>>();
    const seriesKeys: string[] = [];

    for (const item of series) {
      const key = item.name;
      seriesKeys.push(key);
      for (const point of item.points) {
        const existing = byTimestamp.get(point.timestamp) ?? { timestamp: point.timestamp };
        if (point.value !== null) existing[key] = point.value;
        byTimestamp.set(point.timestamp, existing);
      }
    }

    return {
      rows: [...byTimestamp.values()].sort((a, b) =>
        String(a.timestamp).localeCompare(String(b.timestamp)),
      ),
      keys: seriesKeys,
    };
  }, [series]);

  if (rows.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#262b28" strokeDasharray="2 4" vertical={false} />
        <XAxis
          dataKey="timestamp"
          tickFormatter={(value: string) => timeOfDay(value)}
          stroke="#6b756f"
          tick={{ fontSize: 10 }}
          minTickGap={40}
        />
        <YAxis
          stroke="#6b756f"
          tick={{ fontSize: 10 }}
          width={48}
          domain={yDomain ?? ['auto', 'auto']}
          tickFormatter={(value: number) => (unit === '%' ? `${value}` : `${value}`)}
        />
        <Tooltip
          contentStyle={{
            background: '#171b19',
            border: '1px solid #343a36',
            borderRadius: 4,
            fontSize: 11,
          }}
          labelFormatter={(value) => timeOfDay(String(value))}
          formatter={(value: number | string, name: string) => [
            `${typeof value === 'number' ? value.toFixed(2) : value}${unit ? ` ${unit}` : ''}`,
            name,
          ]}
        />
        {showLegend && keys.length > 1 ? (
          <Legend wrapperStyle={{ fontSize: 10, color: '#9aa5a0' }} iconType="line" />
        ) : null}
        {keys.map((key, index) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={PALETTE[index % PALETTE.length]}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
