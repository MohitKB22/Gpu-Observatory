import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { severityClasses } from '@/lib/format';

interface BadgeProps {
  children: ReactNode;
  variant?: 'default' | 'accent' | 'outline';
  className?: string;
}

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded border px-1.5 py-0.5 text-2xs font-medium uppercase tracking-wide',
        variant === 'accent' && 'border-nvidia/40 bg-nvidia-faint text-nvidia',
        variant === 'default' && 'border-line-strong bg-elevated text-ink-muted',
        variant === 'outline' && 'border-line-strong bg-transparent text-ink-muted',
        className,
      )}
    >
      {children}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded border px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide',
        severityClasses(severity),
      )}
    >
      {severity}
    </span>
  );
}
