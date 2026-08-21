'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/cn';
import { useAlertSummary } from '@/hooks/useQueries';

const NAV = [
  { href: '/', label: 'Overview' },
  { href: '/gpu', label: 'GPU Monitor' },
  { href: '/inference', label: 'Inference' },
  { href: '/models', label: 'Models' },
  { href: '/compare', label: 'Comparisons' },
  { href: '/diagnostics', label: 'AI Diagnostics' },
  { href: '/cost', label: 'Cost' },
  { href: '/alerts', label: 'Alerts' },
  { href: '/workloads', label: 'Workloads' },
  { href: '/settings', label: 'Settings' },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const { data: alertSummary } = useAlertSummary();
  const activeAlerts = alertSummary?.active ?? 0;

  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-52 shrink-0 flex-col border-r border-line bg-surface"
    >
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <span aria-hidden className="h-4 w-1 rounded-sm bg-nvidia" />
        <div className="min-w-0 leading-tight">
          <p className="truncate text-xs font-semibold text-ink">NVIDIA</p>
          <p className="truncate text-2xs text-ink-muted">Performance Observatory</p>
        </div>
      </div>

      <ul className="flex-1 overflow-y-auto py-2">
        {NAV.map((item) => {
          const isActive =
            item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={isActive ? 'page' : undefined}
                className={cn(
                  'flex items-center justify-between gap-2 border-l-2 px-4 py-1.5 text-xs transition-colors',
                  'focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-nvidia',
                  isActive
                    ? 'border-nvidia bg-nvidia-faint text-nvidia'
                    : 'border-transparent text-ink-muted hover:bg-elevated hover:text-ink',
                )}
              >
                <span>{item.label}</span>
                {item.href === '/alerts' && activeAlerts > 0 ? (
                  <span className="rounded bg-severity-critical/20 px-1 text-2xs font-semibold text-severity-critical">
                    {activeAlerts}
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>

      <div className="border-t border-line px-4 py-2 text-2xs text-ink-faint">v1.0.0</div>
    </nav>
  );
}
