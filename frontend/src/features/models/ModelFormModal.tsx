import { Eye, EyeOff } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';

import { ApiError } from '@/api/client';
import { createModel, updateModel } from '@/api/endpoints';
import type { Model, ProviderKind } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { Field, Input, Select, Textarea } from '@/components/ui/Form';
import { Modal } from '@/components/ui/Overlay';
import { describedBy } from '@/lib/a11y';
import { PROVIDER_ORDER, PROVIDERS } from '@/lib/constants';
import {
  API_FIELD_TO_FORM,
  EMPTY_FORM,
  formFromModel,
  toCreatePayload,
  toUpdatePayload,
  validateModelForm,
  type ModelFormErrors,
  type ModelFormValues,
} from './modelForm';

interface ModelFormModalProps {
  open: boolean;
  model: Model | null;
  onClose: () => void;
  onSaved: (model: Model, created: boolean) => void;
}

export function ModelFormModal({ open, model, onClose, onSaved }: ModelFormModalProps) {
  // Re-mount the form for each model so its state always starts from that model's values.
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={model ? `Edit ${model.name}` : 'Register a model'}
      description="Endpoint credentials are encrypted on the backend and never sent back to the browser."
      size="lg"
    >
      <ModelForm key={model?.id ?? 'new'} model={model} onCancel={onClose} onSaved={onSaved} />
    </Modal>
  );
}

function ModelForm({
  model,
  onCancel,
  onSaved,
}: {
  model: Model | null;
  onCancel: () => void;
  onSaved: (model: Model, created: boolean) => void;
}) {
  const formId = useId();
  const [values, setValues] = useState<ModelFormValues>(() => (model ? formFromModel(model) : EMPTY_FORM));
  const [errors, setErrors] = useState<ModelFormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showKey, setShowKey] = useState(false);

  const provider = PROVIDERS[values.provider];
  const isDemo = values.provider === 'demo';
  const fieldId = (name: string) => `${formId}-${name}`;

  function update<K extends keyof ModelFormValues>(key: K, value: ModelFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
    if (errors[key]) setErrors((current) => ({ ...current, [key]: undefined }));
  }

  function validateField(key: keyof ModelFormValues) {
    const message = validateModelForm(values)[key];
    setErrors((current) => ({ ...current, [key]: message }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const validation = validateModelForm(values);
    setErrors(validation);
    setFormError(null);
    if (Object.values(validation).some(Boolean)) return;

    setSaving(true);
    try {
      const saved = model ? await updateModel(model.id, toUpdatePayload(values)) : await createModel(toCreatePayload(values));
      onSaved(saved, !model);
    } catch (error) {
      if (error instanceof ApiError) {
        const fieldErrors: ModelFormErrors = {};
        for (const [field, message] of Object.entries(error.fieldErrors)) {
          const formField = API_FIELD_TO_FORM[field];
          if (formField) fieldErrors[formField] = message;
        }
        setErrors(fieldErrors);
        setFormError(Object.keys(fieldErrors).length ? null : [error.message, ...error.formErrors].join(' — '));
      } else {
        setFormError('Could not save the model.');
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      {formError && (
        <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-red-200">
          {formError}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field id={fieldId('name')} label="Display name" required error={errors.name}>
          <Input
            id={fieldId('name')}
            data-autofocus
            value={values.name}
            onChange={(event) => update('name', event.target.value)}
            onBlur={() => validateField('name')}
            invalid={Boolean(errors.name)}
            aria-describedby={describedBy(fieldId('name'), errors.name)}
            placeholder="llama-3.1-8b-prod"
            maxLength={100}
            autoComplete="off"
          />
        </Field>

        <Field id={fieldId('provider')} label="Provider" required hint={provider.description}>
          <Select
            id={fieldId('provider')}
            value={values.provider}
            onChange={(event) => update('provider', event.target.value as ProviderKind)}
            aria-describedby={describedBy(fieldId('provider'), undefined, true)}
          >
            {PROVIDER_ORDER.map((kind) => (
              <option key={kind} value={kind}>
                {PROVIDERS[kind].label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <Field
        id={fieldId('identifier')}
        label="Model ID"
        required
        error={errors.modelIdentifier}
        hint={isDemo ? 'Demo speed profiles: swift-1b, orbit-8b, atlas-70b.' : 'Sent as the "model" field to the endpoint.'}
      >
        <Input
          id={fieldId('identifier')}
          value={values.modelIdentifier}
          onChange={(event) => update('modelIdentifier', event.target.value)}
          onBlur={() => validateField('modelIdentifier')}
          invalid={Boolean(errors.modelIdentifier)}
          aria-describedby={describedBy(fieldId('identifier'), errors.modelIdentifier, true)}
          placeholder={provider.identifierPlaceholder}
          className="font-mono text-xs"
          autoComplete="off"
        />
      </Field>

      {!isDemo && (
        <>
          <Field
            id={fieldId('url')}
            label="Endpoint URL"
            required
            error={errors.endpointUrl}
            hint={values.provider === 'huggingface' ? 'The URL you POST generation requests to.' : 'API base including /v1.'}
          >
            <Input
              id={fieldId('url')}
              type="url"
              inputMode="url"
              value={values.endpointUrl}
              onChange={(event) => update('endpointUrl', event.target.value)}
              onBlur={() => validateField('endpointUrl')}
              invalid={Boolean(errors.endpointUrl)}
              aria-describedby={describedBy(fieldId('url'), errors.endpointUrl, true)}
              placeholder={provider.urlPlaceholder}
              className="font-mono text-xs"
              autoComplete="off"
            />
          </Field>

          <Field
            id={fieldId('key')}
            label="API key"
            error={errors.apiKey}
            hint={
              model?.has_api_key
                ? 'A key is stored. Leave blank to keep it.'
                : 'Optional. Sent as a Bearer token; stored encrypted.'
            }
          >
            <div className="relative">
              <Input
                id={fieldId('key')}
                type={showKey ? 'text' : 'password'}
                value={values.apiKey}
                onChange={(event) => update('apiKey', event.target.value)}
                aria-describedby={describedBy(fieldId('key'), errors.apiKey, true)}
                placeholder={model?.has_api_key ? '••••••••  (unchanged)' : 'sk-…'}
                className="pr-10 font-mono text-xs"
                autoComplete="new-password"
              />
              <button
                type="button"
                onClick={() => setShowKey((shown) => !shown)}
                className="absolute inset-y-0 right-0 flex w-9 cursor-pointer items-center justify-center text-muted hover:text-fg"
                aria-label={showKey ? 'Hide API key' : 'Show API key'}
              >
                {showKey ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
              </button>
            </div>
          </Field>
          {model?.has_api_key && (
            <label className="flex cursor-pointer items-center gap-2 text-xs text-muted">
              <input
                type="checkbox"
                checked={values.clearApiKey}
                onChange={(event) => update('clearApiKey', event.target.checked)}
                className="size-4 cursor-pointer accent-primary"
              />
              Remove the stored API key
            </label>
          )}
        </>
      )}

      <div className="grid gap-4 sm:grid-cols-[160px_1fr]">
        <Field id={fieldId('timeout')} label="Timeout (seconds)" required error={errors.timeoutSeconds}>
          <Input
            id={fieldId('timeout')}
            type="number"
            min={1}
            max={600}
            value={values.timeoutSeconds}
            onChange={(event) => update('timeoutSeconds', event.target.value)}
            onBlur={() => validateField('timeoutSeconds')}
            invalid={Boolean(errors.timeoutSeconds)}
            aria-describedby={describedBy(fieldId('timeout'), errors.timeoutSeconds)}
          />
        </Field>
        <Field id={fieldId('description')} label="Description" error={errors.description}>
          <Textarea
            id={fieldId('description')}
            value={values.description}
            onChange={(event) => update('description', event.target.value)}
            className="min-h-9"
            rows={1}
            maxLength={1000}
            placeholder="Optional notes, owner, region…"
          />
        </Field>
      </div>

      <label className="flex cursor-pointer items-start gap-2 text-xs">
        <input
          type="checkbox"
          checked={values.isEnabled}
          onChange={(event) => update('isEnabled', event.target.checked)}
          className="mt-0.5 size-4 cursor-pointer accent-primary"
        />
        <span>
          <span className="font-medium text-fg">Enabled in the Observatory</span>
          <span className="block text-muted">
            Controls whether the Playground and health checks use this endpoint. It does not deploy or stop the model.
          </span>
        </span>
      </label>

      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={saving}>
          {model ? 'Save changes' : 'Register model'}
        </Button>
      </div>
    </form>
  );
}
