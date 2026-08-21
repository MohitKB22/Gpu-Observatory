'use client';

import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/cn';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
}

export function Button({
  children,
  variant = 'secondary',
  size = 'sm',
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded border font-medium transition-colors',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-nvidia',
        'disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'px-2.5 py-1.5 text-xs' : 'px-3.5 py-2 text-sm',
        variant === 'primary' &&
          'border-nvidia bg-nvidia text-black hover:bg-nvidia-bright disabled:hover:bg-nvidia',
        variant === 'secondary' &&
          'border-line-strong bg-elevated text-ink hover:border-nvidia/50 hover:text-nvidia',
        variant === 'ghost' && 'border-transparent bg-transparent text-ink-muted hover:text-ink',
        variant === 'danger' &&
          'border-severity-critical/50 bg-severity-critical/10 text-severity-critical hover:bg-severity-critical/20',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
