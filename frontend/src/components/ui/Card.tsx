import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/lib/cn';

export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={cn('rounded-xl border border-line bg-card', className)} {...props} />;
}

interface CardHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function CardHeader({ title, description, actions, className }: CardHeaderProps) {
  return (
    <header className={cn('flex flex-wrap items-start justify-between gap-3 px-4 pt-4 pb-3', className)}>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-fg">{title}</h2>
        {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}
