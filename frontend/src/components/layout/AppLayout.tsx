import {
  Activity,
  BarChart3,
  Boxes,
  FlaskConical,
  LayoutDashboard,
  Menu,
  ScrollText,
  Server,
  Terminal,
  X,
} from 'lucide-react';
import { Suspense, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';

import type { DataSource } from '@/api/types';
import { useDataSource } from '@/context/DataSourceContext';
import { DATA_SOURCES } from '@/lib/constants';
import { cn } from '@/lib/cn';
import { Select } from '../ui/Form';
import { Skeleton } from '../ui/States';

const NAVIGATION = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/models', label: 'Model Registry', icon: Boxes },
  { to: '/playground', label: 'Playground', icon: Terminal },
  { to: '/analytics', label: 'Performance', icon: BarChart3 },
  { to: '/infrastructure', label: 'Infrastructure', icon: Server },
  { to: '/logs', label: 'Request Logs', icon: ScrollText },
];

export function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const [menuPath, setMenuPath] = useState(location.pathname);

  // Close the mobile menu after navigating.
  if (menuPath !== location.pathname) {
    setMenuPath(location.pathname);
    setMenuOpen(false);
  }

  return (
    <div className="min-h-screen lg:pl-60">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>

      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />

      <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-canvas/90 px-4 backdrop-blur lg:px-8">
        <button
          type="button"
          className="-ml-1 inline-flex size-9 cursor-pointer items-center justify-center rounded-md text-muted hover:bg-elevated hover:text-fg lg:hidden"
          aria-label="Open navigation"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(true)}
        >
          <Menu className="size-5" aria-hidden />
        </button>
        <Brand className="lg:hidden" />
        <div className="ml-auto flex items-center gap-3">
          <ModeIndicator />
          <DataSourcePicker />
        </div>
      </header>

      <main id="main" className="mx-auto max-w-[1440px] px-4 py-6 lg:px-8">
        <Suspense fallback={<PageSkeleton />}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={onClose} aria-hidden />}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-line bg-sidebar transition-transform duration-200 lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
        aria-label="Primary"
      >
        <div className="flex h-14 items-center justify-between border-b border-line px-4">
          <Brand />
          <button
            type="button"
            className="inline-flex size-8 cursor-pointer items-center justify-center rounded-md text-muted hover:bg-elevated hover:text-fg lg:hidden"
            aria-label="Close navigation"
            onClick={onClose}
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <nav className="flex-1 space-y-0.5 p-3">
          {NAVIGATION.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors duration-150',
                  isActive ? 'bg-elevated text-fg' : 'text-muted hover:bg-elevated/60 hover:text-fg',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={cn('size-4', isActive ? 'text-primary' : 'text-muted')} aria-hidden />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <SidebarFooter />
      </aside>
    </>
  );
}

function Brand({ className }: { className?: string }) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <span className="flex size-7 items-center justify-center rounded-md bg-linear-to-br from-primary to-secondary">
        <Activity className="size-4 text-white" aria-hidden />
      </span>
      <span className="text-sm leading-tight font-semibold">
        Inference
        <span className="block text-[11px] font-medium text-muted">Observatory</span>
      </span>
    </div>
  );
}

function SidebarFooter() {
  const { systemInfo } = useDataSource();
  return (
    <div className="border-t border-line px-4 py-3 text-[11px] text-muted">
      {systemInfo ? (
        <>
          v{systemInfo.version} · {systemInfo.environment}
        </>
      ) : (
        'Connecting…'
      )}
      <a href="/api/docs" className="mt-1 block underline-offset-2 hover:text-fg hover:underline">
        API documentation
      </a>
    </div>
  );
}

function ModeIndicator() {
  const { systemInfo } = useDataSource();
  if (!systemInfo?.demo_mode) return null;
  return (
    <span
      className="hidden items-center gap-1.5 rounded-md border border-secondary/30 bg-secondary/10 px-2 py-1 text-xs font-medium text-violet-300 sm:inline-flex"
      title="DEMO_MODE is on: demo models and labelled sample history are available"
    >
      <FlaskConical className="size-3.5" aria-hidden />
      Demo mode
    </span>
  );
}

function DataSourcePicker() {
  const { dataSource, setDataSource } = useDataSource();
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="data-source" className="hidden text-xs whitespace-nowrap text-muted md:inline">
        Data source
      </label>
      <Select
        id="data-source"
        value={dataSource}
        onChange={(event) => setDataSource(event.target.value as DataSource)}
        className="h-8 w-32 text-xs"
      >
        {DATA_SOURCES.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </Select>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading page">
      <Skeleton className="h-8 w-56" />
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-28" />
        ))}
      </div>
      <Skeleton className="h-72" />
    </div>
  );
}
