/**
 * Typed API client.
 *
 * Handles the token lifecycle (including a single automatic refresh on 401)
 * and converts backend error envelopes into a typed ApiError so every screen
 * can render a real message instead of a generic failure.
 */

import type { ApiErrorBody } from './types';

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') ?? 'http://localhost:8000';

const ACCESS_KEY = 'nvo.access_token';
const REFRESH_KEY = 'nvo.refresh_token';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | undefined;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
    requestId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }

  /** True when the caller must sign in again. */
  get isAuth(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** Network failures and 5xx are worth retrying; 4xx generally are not. */
  get isRetryable(): boolean {
    return this.status === 0 || this.status >= 500 || this.status === 429;
  }
}

export const tokenStore = {
  get access(): string | null {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(ACCESS_KEY);
  },
  get refresh(): string | null {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(ACCESS_KEY, access);
    window.localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    if (typeof window === 'undefined') return;
    window.localStorage.removeItem(ACCESS_KEY);
    window.localStorage.removeItem(REFRESH_KEY);
  },
};

export type QueryParams = Record<string, string | number | boolean | undefined | null>;

function buildUrl(path: string, params?: QueryParams): string {
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = 'http_error';
  let message = `Request failed with status ${response.status}.`;
  let details: Record<string, unknown> = {};
  try {
    const body = (await response.json()) as ApiErrorBody;
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details ?? {};
      return new ApiError(response.status, code, message, details, body.error.request_id);
    }
  } catch {
    // Non-JSON error body: keep the generic message.
  }
  return new ApiError(response.status, code, message, details);
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refresh = tokenStore.refresh;
  if (!refresh) return false;

  // Collapse concurrent 401s into one refresh attempt.
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(buildUrl('/api/v1/auth/refresh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!response.ok) {
        tokenStore.clear();
        return false;
      }
      const tokens = (await response.json()) as { access_token: string; refresh_token: string };
      tokenStore.set(tokens.access_token, tokens.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  params?: QueryParams;
  body?: unknown;
  signal?: AbortSignal;
  retryOnAuthFailure?: boolean;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', params, body, signal, retryOnAuthFailure = true } = options;

  const headers: Record<string, string> = { Accept: 'application/json' };
  const token = tokenStore.access;
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(buildUrl(path, params), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError(
      0,
      'network_error',
      'Cannot reach the API. Check that the backend is running and reachable.',
    );
  }

  if (response.status === 401 && retryOnAuthFailure && tokenStore.refresh) {
    if (await refreshAccessToken()) {
      return apiRequest<T>(path, { ...options, retryOnAuthFailure: false });
    }
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;

  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, params?: QueryParams, signal?: AbortSignal) =>
    apiRequest<T>(path, { params, signal }),
  post: <T>(path: string, body?: unknown, params?: QueryParams) =>
    apiRequest<T>(path, { method: 'POST', body, params }),
  patch: <T>(path: string, body?: unknown, params?: QueryParams) =>
    apiRequest<T>(path, { method: 'PATCH', body, params }),
  delete: <T>(path: string, params?: QueryParams) =>
    apiRequest<T>(path, { method: 'DELETE', params }),
};

/** Health is public and must never carry credentials. */
export async function fetchHealth(signal?: AbortSignal) {
  const response = await fetch(buildUrl('/health'), { signal });
  if (!response.ok) throw await toApiError(response);
  return response.json();
}

export function websocketUrl(channels: string[], dataSource: string): string {
  const base = API_BASE.replace(/^http/, 'ws');
  const params = new URLSearchParams({ channels: channels.join(','), source: dataSource });
  const token = tokenStore.access;
  if (token) params.set('token', token);
  return `${base}/ws/telemetry?${params.toString()}`;
}
