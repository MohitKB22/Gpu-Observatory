import { Play, SlidersHorizontal } from 'lucide-react';
import { useId, useState, type FormEvent, type KeyboardEvent } from 'react';
import { Link } from 'react-router-dom';

import { ApiError, errorMessage } from '@/api/client';
import { listLogs, listModels, runInference } from '@/api/endpoints';
import type { InferenceRecord } from '@/api/types';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { Field, Input, Select, Textarea } from '@/components/ui/Form';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { useApiQuery } from '@/hooks/useApiQuery';
import { describedBy } from '@/lib/a11y';
import { PROVIDERS } from '@/lib/constants';
import { RecentRuns } from './RecentRuns';
import { ResponsePanel } from './ResponsePanel';

const MAX_PROMPT_CHARS = 32_000;

interface PlaygroundSettings {
  modelId: string;
  prompt: string;
  systemPrompt: string;
  temperature: number;
  maxTokens: string;
}

export default function PlaygroundPage() {
  const formId = useId();
  const models = useApiQuery(listModels, []);
  const [runsRevision, setRunsRevision] = useState(0);
  const recentRuns = useApiQuery(
    (signal) => listLogs({ source: 'playground', pageSize: 6, dataSource: 'all' }, signal),
    [runsRevision],
  );

  const [settings, setSettings] = useState<PlaygroundSettings>({
    modelId: '',
    prompt: '',
    systemPrompt: '',
    temperature: 0.7,
    maxTokens: '256',
  });
  const [showSystemPrompt, setShowSystemPrompt] = useState(false);
  const [errors, setErrors] = useState<{ modelId?: string; prompt?: string; maxTokens?: string }>({});
  const [running, setRunning] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [result, setResult] = useState<InferenceRecord | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  const enabledModels = (models.data ?? []).filter((model) => model.is_enabled);
  // Default to the first enabled model until the user picks one.
  const selectedModelId = settings.modelId || enabledModels[0]?.id || '';
  const selectedModel = enabledModels.find((model) => model.id === selectedModelId);
  const fieldId = (name: string) => `${formId}-${name}`;

  function update<K extends keyof PlaygroundSettings>(key: K, value: PlaygroundSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  }

  function validate() {
    const maxTokens = Number(settings.maxTokens);
    const next = {
      modelId: selectedModelId ? undefined : 'Choose a model.',
      prompt: settings.prompt.trim() ? undefined : 'Enter a prompt.',
      maxTokens: Number.isInteger(maxTokens) && maxTokens >= 1 && maxTokens <= 8192 ? undefined : 'Use a whole number from 1 to 8192.',
    };
    setErrors(next);
    return !next.modelId && !next.prompt && !next.maxTokens;
  }

  async function handleRun(event?: FormEvent) {
    event?.preventDefault();
    if (running || !validate()) return;
    setRunning(true);
    setStartedAt(Date.now());
    setRequestError(null);
    try {
      const record = await runInference({
        model_id: selectedModelId,
        prompt: settings.prompt,
        system_prompt: settings.systemPrompt.trim() || null,
        temperature: settings.temperature,
        max_tokens: Number(settings.maxTokens),
        source: 'playground',
      });
      setResult(record);
      setRunsRevision((value) => value + 1);
    } catch (error) {
      setResult(null);
      setRequestError(
        error instanceof ApiError && error.details.length
          ? error.details.map((detail) => detail.message).join(' ')
          : errorMessage(error),
      );
    } finally {
      setRunning(false);
    }
  }

  function handlePromptKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void handleRun();
    }
  }

  if (models.error && !models.data) return <ErrorState error={models.error} onRetry={models.refetch} />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Inference Playground"
        description="Send a prompt to a registered model and inspect the response with measured latency and token usage."
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <Card>
          <CardHeader title="Request" description="Every run is recorded in Request Logs and Performance Analytics." />
          {!models.data ? (
            <div className="space-y-3 px-4 pb-4">
              <Skeleton className="h-9" />
              <Skeleton className="h-40" />
            </div>
          ) : enabledModels.length === 0 ? (
            <EmptyState
              title="No enabled models"
              description="Register a model, or enable one in the Model Registry, to run prompts."
              action={
                <Link to="/models" className="text-xs font-medium text-blue-300 hover:underline">
                  Open Model Registry
                </Link>
              }
            />
          ) : (
            <form onSubmit={handleRun} noValidate className="space-y-4 px-4 pb-4">
              <Field
                id={fieldId('model')}
                label="Model"
                required
                error={errors.modelId}
                hint={selectedModel ? `${PROVIDERS[selectedModel.provider].label} · ${selectedModel.model_identifier}` : undefined}
              >
                <Select
                  id={fieldId('model')}
                  value={selectedModelId}
                  onChange={(event) => update('modelId', event.target.value)}
                  invalid={Boolean(errors.modelId)}
                  aria-describedby={describedBy(fieldId('model'), errors.modelId, true)}
                >
                  {enabledModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name}
                      {model.is_demo ? ' (demo)' : ''}
                    </option>
                  ))}
                </Select>
              </Field>

              {showSystemPrompt ? (
                <Field id={fieldId('system')} label="System prompt" hint="Optional instructions sent before the prompt.">
                  <Textarea
                    id={fieldId('system')}
                    value={settings.systemPrompt}
                    onChange={(event) => update('systemPrompt', event.target.value)}
                    rows={3}
                    maxLength={8000}
                    aria-describedby={`${fieldId('system')}-hint`}
                    placeholder="You are a concise assistant."
                  />
                </Field>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowSystemPrompt(true)}
                  className="cursor-pointer text-xs font-medium text-blue-300 hover:underline"
                >
                  + Add a system prompt
                </button>
              )}

              <Field
                id={fieldId('prompt')}
                label="Prompt"
                required
                error={errors.prompt}
                hint={`${settings.prompt.length.toLocaleString()} / ${MAX_PROMPT_CHARS.toLocaleString()} characters · Ctrl+Enter to run`}
              >
                <Textarea
                  id={fieldId('prompt')}
                  value={settings.prompt}
                  onChange={(event) => update('prompt', event.target.value)}
                  onKeyDown={handlePromptKeyDown}
                  invalid={Boolean(errors.prompt)}
                  aria-describedby={describedBy(fieldId('prompt'), errors.prompt, true)}
                  rows={8}
                  maxLength={MAX_PROMPT_CHARS}
                  placeholder="Explain the difference between P95 and P99 latency."
                  className="font-mono text-xs"
                />
              </Field>

              <fieldset className="grid gap-4 rounded-lg border border-line p-3 sm:grid-cols-2">
                <legend className="flex items-center gap-1.5 px-1 text-xs font-medium text-muted">
                  <SlidersHorizontal className="size-3.5" aria-hidden />
                  Parameters
                </legend>
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <label htmlFor={fieldId('temperature')} className="text-xs font-medium">
                      Temperature
                    </label>
                    <output htmlFor={fieldId('temperature')} className="font-mono text-xs text-muted tabular-nums">
                      {settings.temperature.toFixed(1)}
                    </output>
                  </div>
                  <input
                    id={fieldId('temperature')}
                    type="range"
                    min={0}
                    max={2}
                    step={0.1}
                    value={settings.temperature}
                    onChange={(event) => update('temperature', Number(event.target.value))}
                    className="h-9 w-full cursor-pointer accent-primary"
                  />
                </div>
                <Field id={fieldId('max-tokens')} label="Max tokens" error={errors.maxTokens}>
                  <Input
                    id={fieldId('max-tokens')}
                    type="number"
                    min={1}
                    max={8192}
                    step={1}
                    value={settings.maxTokens}
                    onChange={(event) => update('maxTokens', event.target.value)}
                    invalid={Boolean(errors.maxTokens)}
                    aria-describedby={describedBy(fieldId('max-tokens'), errors.maxTokens)}
                  />
                </Field>
              </fieldset>

              <div className="flex justify-end">
                <Button type="submit" variant="primary" loading={running} icon={<Play className="size-4" aria-hidden />}>
                  {running ? 'Running…' : 'Run inference'}
                </Button>
              </div>
            </form>
          )}
        </Card>

        <ResponsePanel result={result} running={running} startedAt={startedAt} requestError={requestError} />
      </div>

      <RecentRuns query={recentRuns} />
    </div>
  );
}
