import { FlaskConical } from 'lucide-react';
import type { ReactNode } from 'react';

import type { ProviderKind } from '@/api/types';
import { PROVIDERS } from '@/lib/constants';
import { cn } from '@/lib/cn';

export type BadgeTone = 'neutral' | 'primary' | 'violet' | 'success' | 'warning' | 'danger';

const tones: Record<BadgeTone, string> = {
  neutral: 'border-line bg-elevated text-muted',
  primary: 'border-primary/30 bg-primary/10 text-blue-300',
  violet: 'border-secondary/30 bg-secondary/10 text-violet-300',
  success: 'border-success/30 bg-success/10 text-green-300',
  warning: 'border-warning/30 bg-warning/10 text-amber-300',
  danger: 'border-danger/30 bg-danger/10 text-red-300',
};

interface BadgeProps {
  tone?: BadgeTone;
  icon?: ReactNode;
  title?: string;
  className?: string;
  children: ReactNode;
}

export function Badge({ tone = 'neutral', icon, title, className, children }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] leading-4 font-medium whitespace-nowrap',
        tones[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

export function DemoBadge({ label = 'Demo' }: { label?: string }) {
  return (
    <Badge tone="violet" icon={<FlaskConical className="size-3" aria-hidden />} title="Simulated by the local demo provider">
      {label}
    </Badge>
  );
}

export function ProviderBadge({ provider }: { provider: ProviderKind }) {
  return <Badge tone={provider === 'demo' ? 'violet' : 'neutral'}>{PROVIDERS[provider].label}</Badge>;
}

export function TokenSourceBadge({ source }: { source: string | null }) {
  if (!source) return null;
  return source === 'exact' ? (
    <Badge tone="success" title="Reported by the provider">
      exact
    </Badge>
  ) : (
    <Badge tone="warning" title="Estimated from text length (~4 characters per token)">
      estimated
    </Badge>
  );
}
