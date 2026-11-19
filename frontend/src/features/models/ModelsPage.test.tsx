import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { buildModel, jsonResponse, mockApi, renderWithProviders, systemInfo } from '@/test/utils';
import ModelsPage from './ModelsPage';

describe('ModelsPage', () => {
  it('lists registered models with status and demo labels', async () => {
    mockApi({
      'GET /api/system/info': systemInfo,
      'GET /api/models': [
        buildModel(),
        buildModel({ id: 'demo', name: 'demo-orbit-8b', provider: 'demo', is_demo: true, endpoint_url: null, status: 'unknown', last_checked_at: null }),
      ],
    });
    renderWithProviders(<ModelsPage />);

    const realRow = (await screen.findByText('gpt-proxy')).closest('tr')!;
    expect(within(realRow).getByText('Healthy')).toBeInTheDocument();
    const demoRow = screen.getByText('demo-orbit-8b').closest('tr')!;
    expect(within(demoRow).getByText('Demo')).toBeInTheDocument();
    expect(within(demoRow).getByText('Not checked')).toBeInTheDocument();
  });

  it('validates the registration form inline, then submits the expected payload', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/system/info': systemInfo,
      'GET /api/models': [],
      'POST /api/models': ({ body }: { body: unknown }) => buildModel({ ...(body as object), id: 'new-id' }),
    });
    renderWithProviders(<ModelsPage />);

    await user.click((await screen.findAllByRole('button', { name: 'Register model' }))[0]);
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Register model' }));

    expect(within(dialog).getByText('Enter a name.')).toBeInTheDocument();
    expect(within(dialog).getByText('An endpoint URL is required for this provider.')).toBeInTheDocument();
    expect(calls.some((call) => call.method === 'POST')).toBe(false);

    await user.type(within(dialog).getByLabelText(/Display name/), 'vllm-prod');
    await user.selectOptions(within(dialog).getByLabelText(/Provider/), 'vllm');
    await user.type(within(dialog).getByLabelText(/Model ID/), 'llama-3.1-8b');
    await user.type(within(dialog).getByLabelText(/Endpoint URL/), 'http://gpu:8000/v1');
    await user.type(within(dialog).getByLabelText('API key'), 'secret');
    await user.click(within(dialog).getByRole('button', { name: 'Register model' }));

    await screen.findByText('vllm-prod registered');
    const post = calls.find((call) => call.method === 'POST')!;
    expect(post.body).toEqual({
      name: 'vllm-prod',
      provider: 'vllm',
      model_identifier: 'llama-3.1-8b',
      endpoint_url: 'http://gpu:8000/v1',
      api_key: 'secret',
      timeout_seconds: 60,
      description: null,
      is_enabled: true,
    });
  });

  it('shows server-side conflicts in the form', async () => {
    const user = userEvent.setup();
    mockApi({
      'GET /api/system/info': systemInfo,
      'GET /api/models': [],
      'POST /api/models': () =>
        jsonResponse({ error: { code: 'conflict', message: 'A model named "dup" already exists' } }, 409),
    });
    renderWithProviders(<ModelsPage />);

    await user.click((await screen.findAllByRole('button', { name: 'Register model' }))[0]);
    const dialog = screen.getByRole('dialog');
    await user.selectOptions(within(dialog).getByLabelText(/Provider/), 'demo');
    await user.type(within(dialog).getByLabelText(/Display name/), 'dup');
    await user.type(within(dialog).getByLabelText(/Model ID/), 'orbit-8b');
    await user.click(within(dialog).getByRole('button', { name: 'Register model' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('A model named "dup" already exists');
  });

  it('runs a connection check and reports a failure', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/system/info': systemInfo,
      'GET /api/models': [buildModel()],
      'POST /api/models/model-1/check': {
        check: { id: 1, checked_at: new Date().toISOString(), status: 'unhealthy', latency_ms: 12, error_kind: 'auth', error_message: 'Endpoint rejected the credentials (HTTP 401)' },
        model: buildModel({ status: 'unhealthy' }),
      },
    });
    renderWithProviders(<ModelsPage />);

    await user.click(await screen.findByRole('button', { name: 'Check connection' }));

    expect(await screen.findByText('gpt-proxy failed the check')).toBeInTheDocument();
    expect(screen.getByText('Endpoint rejected the credentials (HTTP 401)')).toBeInTheDocument();
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1);
  });

  it('toggles a model with a PATCH request', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/system/info': systemInfo,
      'GET /api/models': [buildModel()],
      'PATCH /api/models/model-1': buildModel({ is_enabled: false }),
    });
    renderWithProviders(<ModelsPage />);

    await user.click(await screen.findByRole('switch', { name: /Disable gpt-proxy/ }));

    await waitFor(() => expect(calls.find((call) => call.method === 'PATCH')?.body).toEqual({ is_enabled: false }));
  });

  it('is read-only in a public demo', async () => {
    mockApi({
      'GET /api/system/info': { ...systemInfo, public_demo: true },
      'GET /api/models': [buildModel()],
    });
    renderWithProviders(<ModelsPage />);

    expect(await screen.findByText(/This public demo shows the registry read-only/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Check connection' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Register model' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit gpt-proxy' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete gpt-proxy' })).not.toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });
});
