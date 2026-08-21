'use client';

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const PALETTE = ['#76b900', '#5b9dd9', '#d9a441', '#e0703c', '#9b8bd6', '#4fb286'];

export interface ComparisonRow {
  metric: string;
  [modelName: string]: string | number;
}

export function ComparisonBarChart({
  rows,
  models,
  height = 260,
}: {
  rows: ComparisonRow[];
  models: string[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#262b28" strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey="metric" stroke="#6b756f" tick={{ fontSize: 10 }} />
        <YAxis stroke="#6b756f" tick={{ fontSize: 10 }} width={48} />
        <Tooltip
          cursor={{ fill: 'rgba(118,185,0,0.08)' }}
          contentStyle={{
            background: '#171b19',
            border: '1px solid #343a36',
            borderRadius: 4,
            fontSize: 11,
          }}
        />
        <Legend wrapperStyle={{ fontSize: 10, color: '#9aa5a0' }} />
        {models.map((model, index) => (
          <Bar
            key={model}
            dataKey={model}
            fill={PALETTE[index % PALETTE.length]}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
