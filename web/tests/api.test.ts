import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest, tokenStore, websocketUrl } from '@/lib/api';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  tokenStore.clear();
});

describe('api client', () => {
  it('parses the backend error envelope into a typed error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: 'validation_error',
              message: 'Request validation failed.',
              details: { field: 'name' },
              request_id: 'req-123',
            },
          },
          422,
        ),
      ),
    );

    await expect(apiRequest('/api/v1/models')).rejects.toMatchObject({
      status: 422,
      code: 'validation_error',
      message: 'Request validation failed.',
      requestId: 'req-123',
    });
  });

  it('classifies which failures are worth retrying', () => {
    expect(new ApiError(500, 'x', 'y').isRetryable).toBe(true);
    expect(new ApiError(0, 'network_error', 'y').isRetryable).toBe(true);
    expect(new ApiError(429, 'rate_limited', 'y').isRetryable).toBe(true);
    expect(new ApiError(404, 'not_found', 'y').isRetryable).toBe(false);
    expect(new ApiError(401, 'unauthenticated', 'y').isAuth).toBe(true);
    expect(new ApiError(403, 'forbidden', 'y').isForbidden).toBe(true);
  });

  it('reports an unreachable backend as a network error rather than throwing raw', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(apiRequest('/health')).rejects.toMatchObject({
      status: 0,
      code: 'network_error',
    });
  });

  it('attaches the bearer token when one is stored', async () => {
    tokenStore.set('access-abc', 'refresh-xyz');
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await apiRequest('/api/v1/gpus');
    const call = fetchMock.mock.calls[0];
    expect(call).toBeDefined();
    const headers = (call![1] as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer access-abc');
  });

  it('refreshes once on 401 and retries the original request', async () => {
    tokenStore.set('expired', 'refresh-xyz');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'unauthenticated', message: 'expired' } }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: 'fresh', refresh_token: 'r2' }))
      .mockResolvedValueOnce(jsonResponse({ items: [] }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiRequest('/api/v1/gpus')).resolves.toEqual({ items: [] });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(tokenStore.access).toBe('fresh');
  });

  it('gives up when the refresh itself fails', async () => {
    tokenStore.set('expired', 'bad-refresh');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'unauthenticated', message: 'expired' } }, 401))
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'unauthenticated', message: 'no' } }, 401));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiRequest('/api/v1/gpus')).rejects.toMatchObject({ status: 401 });
    expect(tokenStore.access).toBeNull();
  });

  it('omits empty query parameters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal('fetch', fetchMock);

    await apiRequest('/api/v1/models', { params: { source: 'demo', search: '', limit: undefined } });
    const call = fetchMock.mock.calls[0];
    expect(call).toBeDefined();
    const url = String(call![0]);
    expect(url).toContain('source=demo');
    expect(url).not.toContain('search=');
    expect(url).not.toContain('limit=');
  });

  it('builds a websocket url carrying the token', () => {
    tokenStore.set('tok-1', 'r');
    const url = websocketUrl(['telemetry'], 'demo');
    expect(url).toMatch(/^ws/);
    expect(url).toContain('channels=telemetry');
    expect(url).toContain('source=demo');
    expect(url).toContain('token=tok-1');
  });
});
