import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import type { Model, SystemInfo } from '@/api/types';
import { DataSourceProvider } from '@/context/DataSourceContext';
import { ToastProvider } from '@/context/ToastContext';

type RouteHandler = (request: { url: URL; body: unknown }) => unknown;

/**
 * Replace fetch with a router keyed by "METHOD /path". Handlers return a JSON body, or a
 * Response for full control. Unmatched requests fail loudly so tests never hit the network.
 */
export function mockApi(routes: Record<string, RouteHandler | unknown>) {
  const calls: { method: string; url: URL; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost');
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, url, body });

    const key = `${method} ${url.pathname}`;
    if (!(key in routes)) throw new Error(`Unexpected request in test: ${key}`);
    const route = routes[key];
    const result = typeof route === 'function' ? (route as RouteHandler)({ url, body }) : route;
    if (result instanceof Response) return result;
    return new Response(JSON.stringify(result), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, calls };
}

export function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

export function renderWithProviders(ui: ReactElement, { route = '/' }: { route?: string } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ToastProvider>
        <DataSourceProvider>{ui}</DataSourceProvider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

export const systemInfo: SystemInfo = {
  version: '1.0.0',
  environment: 'test',
  demo_mode: true,
  default_data_source: 'all',
  public_demo: false,
  public_demo_source_url: null,
  max_prompt_chars: 32_000,
  max_tokens: 8192,
};

export function buildModel(overrides: Partial<Model> = {}): Model {
  return {
    id: 'model-1',
    name: 'gpt-proxy',
    provider: 'openai_compatible',
    model_identifier: 'gpt-4o-mini',
    endpoint_url: 'https://api.example.com/v1',
    has_api_key: true,
    timeout_seconds: 60,
    description: null,
    is_enabled: true,
    is_demo: false,
    status: 'healthy',
    last_checked_at: new Date().toISOString(),
    last_check_latency_ms: 42,
    last_error: null,
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    ...overrides,
  };
}
