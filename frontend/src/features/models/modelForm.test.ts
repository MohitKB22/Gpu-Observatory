import { describe, expect, it } from 'vitest';

import { buildModel } from '@/test/utils';
import { EMPTY_FORM, formFromModel, toCreatePayload, toUpdatePayload, validateModelForm } from './modelForm';

describe('validateModelForm', () => {
  it('requires a name, model ID and endpoint for remote providers', () => {
    const errors = validateModelForm(EMPTY_FORM);
    expect(errors.name).toBeDefined();
    expect(errors.modelIdentifier).toBeDefined();
    expect(errors.endpointUrl).toBe('An endpoint URL is required for this provider.');
  });

  it('rejects non-http URLs and out-of-range timeouts', () => {
    const errors = validateModelForm({
      ...EMPTY_FORM,
      name: 'x',
      modelIdentifier: 'm',
      endpointUrl: 'ftp://example.com',
      timeoutSeconds: '0',
    });
    expect(errors.endpointUrl).toBe('Enter a full http:// or https:// URL.');
    expect(errors.timeoutSeconds).toBeDefined();
  });

  it('does not require an endpoint for the demo provider', () => {
    const errors = validateModelForm({ ...EMPTY_FORM, provider: 'demo', name: 'demo', modelIdentifier: 'orbit-8b' });
    expect(errors).toEqual({});
  });
});

describe('payload builders', () => {
  it('omits the endpoint for demo models and blank optional fields', () => {
    const payload = toCreatePayload({
      ...EMPTY_FORM,
      provider: 'demo',
      name: '  demo  ',
      modelIdentifier: 'orbit-8b',
      endpointUrl: 'http://ignored',
    });
    expect(payload).toEqual({
      name: 'demo',
      provider: 'demo',
      model_identifier: 'orbit-8b',
      endpoint_url: null,
      timeout_seconds: 60,
      description: null,
      is_enabled: true,
    });
  });

  it('keeps the stored API key on update unless a new one is entered or removal is requested', () => {
    const values = formFromModel(buildModel());
    expect(toUpdatePayload(values)).not.toHaveProperty('api_key');
    expect(toUpdatePayload(values)).not.toHaveProperty('clear_api_key');
    expect(toUpdatePayload({ ...values, apiKey: 'new' }).api_key).toBe('new');
    expect(toUpdatePayload({ ...values, clearApiKey: true }).clear_api_key).toBe(true);
  });
});
