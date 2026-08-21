'use client';

import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';
import { ApiError, api, tokenStore } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import type { TokenPair } from '@/lib/types';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const tokens = await api.post<TokenPair>('/api/v1/auth/login', { email, password });
      tokenStore.set(tokens.access_token, tokens.refresh_token);
      router.replace('/');
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : 'Sign-in failed. Check that the backend is reachable.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas p-6">
      <div className="w-full max-w-sm rounded border border-line bg-surface p-6">
        <div className="mb-5 flex items-center gap-2">
          <span aria-hidden className="h-5 w-1 rounded-sm bg-nvidia" />
          <div>
            <h1 className="text-sm font-semibold text-ink">NVIDIA AI Performance Observatory</h1>
            <p className="text-2xs text-ink-muted">Sign in to continue</p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-3">
          <div>
            <label htmlFor="email" className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded border border-line-strong bg-elevated px-2.5 py-2 text-xs text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-nvidia"
            />
          </div>
          <div>
            <label
              htmlFor="password"
              className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded border border-line-strong bg-elevated px-2.5 py-2 text-xs text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-nvidia"
            />
          </div>

          {error ? (
            <p
              role="alert"
              className="rounded border border-severity-critical/30 bg-severity-critical/5 px-2.5 py-2 text-xs text-severity-critical"
            >
              {error}
            </p>
          ) : null}

          <Button type="submit" variant="primary" size="md" disabled={submitting} className="w-full">
            {submitting ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        <p className="mt-4 text-2xs leading-relaxed text-ink-faint">
          The first administrator is created from BOOTSTRAP_ADMIN_EMAIL and
          BOOTSTRAP_ADMIN_PASSWORD on first start. Machine clients should use an API key rather
          than a password.
        </p>
      </div>
    </div>
  );
}
