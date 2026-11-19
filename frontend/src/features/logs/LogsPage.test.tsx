import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { LogListItem } from '@/api/types';
import { buildModel, mockApi, renderWithProviders, systemInfo } from '@/test/utils';
import LogsPage from './LogsPage';

function logItem(index: number, overrides: Partial<LogListItem> = {}): LogListItem {
  return {
    id: `req-${index}`,
    created_at: new Date(Date.now() - index * 60_000).toISOString(),
    model_id: 'model-1',
    model_name: 'gpt-proxy',
    provider: 'openai_compatible',
    source: 'api',
    is_demo: false,
    status: 'success',
    prompt_preview: `Prompt number ${index}`,
    error_kind: null,
    latency_ms: 500 + index,
    total_tokens: 30,
    token_count_source: 'exact',
    tokens_per_second: 40,
    ...overrides,
  };
}

function setup() {
  return mockApi({
    'GET /api/system/info': systemInfo,
    'GET /api/models': [buildModel()],
    'GET /api/logs': ({ url }: { url: URL }) => {
      const page = Number(url.searchParams.get('page') ?? 1);
      const items =
        url.searchParams.get('status') === 'error'
          ? [logItem(99, { status: 'error', error_kind: 'http', prompt_preview: 'Failing prompt' })]
          : [logItem(page * 10 + 1), logItem(page * 10 + 2, { is_demo: true, token_count_source: 'estimated' })];
      return { items, total: 60, page, page_size: 25 };
    },
    'GET /api/logs/req-11': {
      ...logItem(11),
      prompt: 'Full prompt text for request 11',
      system_prompt: null,
      response_text: 'Full response text',
      temperature: 0.2,
      max_tokens: 128,
      error_message: null,
      upstream_status_code: 200,
      metrics: { latency_ms: 511, prompt_tokens: 10, completion_tokens: 20, total_tokens: 30, token_count_source: 'exact', tokens_per_second: 40 },
    },
  });
}

describe('LogsPage', () => {
  it('renders rows with demo and estimated-token markers', async () => {
    setup();
    renderWithProviders(<LogsPage />, { route: '/logs' });

    expect(await screen.findByText('Prompt number 11')).toBeInTheDocument();
    expect(screen.getByText('Demo')).toBeInTheDocument();
    expect(screen.getByText('~30')).toBeInTheDocument();
    expect(screen.getByText('1–25 of 60')).toBeInTheDocument();
  });

  it('sends filters and pagination to the API', async () => {
    const user = userEvent.setup();
    const { calls } = setup();
    renderWithProviders(<LogsPage />, { route: '/logs' });
    await screen.findByText('Prompt number 11');

    await user.selectOptions(screen.getByLabelText('Status'), 'error');
    expect(await screen.findByText('Failing prompt')).toBeInTheDocument();
    expect(calls.at(-1)!.url.searchParams.get('status')).toBe('error');

    await user.selectOptions(screen.getByLabelText('Status'), '');
    await screen.findByText('Prompt number 11');
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(await screen.findByText('Prompt number 21')).toBeInTheDocument();
    expect(calls.at(-1)!.url.searchParams.get('page')).toBe('2');
  });

  it('debounces search input into the query', async () => {
    const user = userEvent.setup();
    const { calls } = setup();
    renderWithProviders(<LogsPage />, { route: '/logs' });
    await screen.findByText('Prompt number 11');

    await user.type(screen.getByLabelText(/Search prompts/), 'timeout');

    await waitFor(() => expect(calls.at(-1)!.url.searchParams.get('search')).toBe('timeout'));
    const searchCalls = calls.filter((call) => call.url.pathname === '/api/logs' && call.url.searchParams.has('search'));
    expect(searchCalls.length).toBeLessThanOrEqual(2);
  });

  it('opens the detail drawer with the full record', async () => {
    const user = userEvent.setup();
    setup();
    renderWithProviders(<LogsPage />, { route: '/logs' });

    const [firstRow] = await screen.findAllByRole('button', { name: /View request from .* to gpt-proxy/ });
    await user.click(firstRow);

    const drawer = await screen.findByRole('dialog', { name: 'Request details' });
    expect(await screen.findByText('Full prompt text for request 11')).toBeInTheDocument();
    expect(drawer).toHaveTextContent('Full response text');
    expect(drawer).toHaveTextContent('exact');
  });
});
