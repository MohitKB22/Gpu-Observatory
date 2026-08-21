'use client';

import { useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';
import { tokenStore } from '@/lib/api';
import { useAuthConfig } from '@/hooks/useQueries';
import { LoadingState } from '@/components/states/States';

/**
 * Redirects to the login screen when authentication is enabled and no token is
 * held. When the backend reports auth disabled (local development) the gate is
 * transparent.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { data: config, isLoading, isError } = useAuthConfig();
  const hasToken = typeof window !== 'undefined' && Boolean(tokenStore.access);
  const mustSignIn = config?.auth_enabled === true && !hasToken;

  useEffect(() => {
    if (mustSignIn) router.replace('/login');
  }, [mustSignIn, router]);

  // If the config call itself fails the backend is unreachable; render the app
  // so each panel can surface its own connection error rather than blocking.
  if (isLoading && !isError) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="w-64">
          <LoadingState label="Loading application" rows={2} />
        </div>
      </div>
    );
  }

  if (mustSignIn) return null;
  return <>{children}</>;
}
