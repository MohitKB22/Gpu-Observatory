'use client';

import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { AuthGate } from './AuthGate';
import { ErrorBoundary } from '@/components/states/ErrorBoundary';

/** The login screen renders without the dashboard chrome. */
export function AppFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  if (pathname === '/login') {
    return <main id="main-content">{children}</main>;
  }

  return (
    <AuthGate>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <main id="main-content" className="flex-1 overflow-y-auto p-4">
            <ErrorBoundary label="This page failed to render">{children}</ErrorBoundary>
          </main>
        </div>
      </div>
    </AuthGate>
  );
}
