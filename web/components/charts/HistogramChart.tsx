'use client';

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { LatencyBucket } from '@/lib/types';

/** Latency distribution. The final open-ended bucket collects the tail. */
export function HistogramChart({ buckets, height = 220 }: { buckets: LatencyBucket[]; height?: number }) {
  const rows = buckets.map((bucket) => ({
    label:
      bucket.upper_ms === null
        ? `>${bucket.lower_ms.toFixed(0)}`
        : `${bucket.lower_ms.toFixed(0)}`,
    count: bucket.count,
    range:
      bucket.upper_ms === null
        ? `over ${bucket.lower_ms.toFixed(0)} ms`
        : `${bucket.lower_ms.toFixed(0)}–${bucket.upper_ms.toFixed(0)} ms`,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#262b28" strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey="label" stroke="#6b756f" tick={{ fontSize: 10 }} minTickGap={16} />
        <YAxis stroke="#6b756f" tick={{ fontSize: 10 }} width={48} />
        <Tooltip
          cursor={{ fill: 'rgba(118,185,0,0.08)' }}
          contentStyle={{
            background: '#171b19',
            border: '1px solid #343a36',
            borderRadius: 4,
            fontSize: 11,
          }}
          labelFormatter={(_label, payload) => payload?.[0]?.payload?.range ?? ''}
          formatter={(value: number) => [`${value} requests`, 'count']}
        />
        <Bar dataKey="count" fill="#76b900" isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
