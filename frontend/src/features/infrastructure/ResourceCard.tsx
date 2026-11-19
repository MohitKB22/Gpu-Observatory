import type { ReactNode } from 'react';

import { ProgressBar } from '@/components/ui/States';

interface ResourceCardProps {
  icon: ReactNode;
  label: string;
  value: string;
  percent?: number | null;
  details: string[];
}

export function ResourceCard({ icon, label, value, percent, details }: ResourceCardProps) {
  return (
    <div className="rounded-xl border border-line bg-card p-4">
      <div className="flex items-center justify-between text-xs font-medium text-muted">
        {label}
        <span aria-hidden>{icon}</span>
      </div>
      <p className="mt-2 font-mono text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
      {percent !== undefined && <ProgressBar value={percent} label={`${label} utilisation`} className="mt-3" />}
      <ul className="mt-3 space-y-0.5 text-xs text-muted">
        {details.map((detail) => (
          <li key={detail}>{detail}</li>
        ))}
      </ul>
    </div>
  );
}
