import type { Model, ModelCreatePayload, ModelUpdatePayload, ProviderKind } from '@/api/types';

export interface ModelFormValues {
  name: string;
  provider: ProviderKind;
  modelIdentifier: string;
  endpointUrl: string;
  apiKey: string;
  clearApiKey: boolean;
  timeoutSeconds: string;
  description: string;
  isEnabled: boolean;
}

export type ModelFormErrors = Partial<Record<keyof ModelFormValues, string>>;

export const EMPTY_FORM: ModelFormValues = {
  name: '',
  provider: 'openai_compatible',
  modelIdentifier: '',
  endpointUrl: '',
  apiKey: '',
  clearApiKey: false,
  timeoutSeconds: '60',
  description: '',
  isEnabled: true,
};

export function formFromModel(model: Model): ModelFormValues {
  return {
    name: model.name,
    provider: model.provider,
    modelIdentifier: model.model_identifier,
    endpointUrl: model.endpoint_url ?? '',
    apiKey: '',
    clearApiKey: false,
    timeoutSeconds: String(model.timeout_seconds),
    description: model.description ?? '',
    isEnabled: model.is_enabled,
  };
}

/** Client-side checks mirror the API's rules so most mistakes are caught before submitting. */
export function validateModelForm(values: ModelFormValues): ModelFormErrors {
  const errors: ModelFormErrors = {};
  if (!values.name.trim()) errors.name = 'Enter a name.';
  else if (values.name.trim().length > 100) errors.name = 'Use 100 characters or fewer.';

  if (!values.modelIdentifier.trim()) errors.modelIdentifier = 'Enter the model ID the endpoint expects.';

  if (values.provider !== 'demo') {
    const url = values.endpointUrl.trim();
    if (!url) errors.endpointUrl = 'An endpoint URL is required for this provider.';
    else if (!isHttpUrl(url)) errors.endpointUrl = 'Enter a full http:// or https:// URL.';
  }

  const timeout = Number(values.timeoutSeconds);
  if (!Number.isFinite(timeout) || timeout < 1 || timeout > 600) errors.timeoutSeconds = 'Use a value from 1 to 600 seconds.';

  return errors;
}

export function toCreatePayload(values: ModelFormValues): ModelCreatePayload {
  return {
    name: values.name.trim(),
    provider: values.provider,
    model_identifier: values.modelIdentifier.trim(),
    endpoint_url: values.provider === 'demo' ? null : values.endpointUrl.trim(),
    ...(values.apiKey ? { api_key: values.apiKey } : {}),
    timeout_seconds: Number(values.timeoutSeconds),
    description: values.description.trim() || null,
    is_enabled: values.isEnabled,
  };
}

export function toUpdatePayload(values: ModelFormValues): ModelUpdatePayload {
  const { api_key, ...rest } = toCreatePayload(values);
  return {
    ...rest,
    // Leaving the key field blank keeps the stored key.
    ...(api_key ? { api_key } : {}),
    ...(values.clearApiKey && !api_key ? { clear_api_key: true } : {}),
  };
}

/** Map API field names back to form fields for server-side validation messages. */
export const API_FIELD_TO_FORM: Record<string, keyof ModelFormValues> = {
  name: 'name',
  provider: 'provider',
  model_identifier: 'modelIdentifier',
  endpoint_url: 'endpointUrl',
  api_key: 'apiKey',
  timeout_seconds: 'timeoutSeconds',
  description: 'description',
};

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return (url.protocol === 'http:' || url.protocol === 'https:') && Boolean(url.hostname);
  } catch {
    return false;
  }
}
