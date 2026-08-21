'use client';

import { useState, type FormEvent } from 'react';
import { PageShell } from '@/components/shell/PageShell';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Table, TD, TH, THead, TR } from '@/components/ui/Table';
import { EmptyState, ErrorState, LoadingState } from '@/components/states/States';
import { useDeployments, useModelPerformance, useModels } from '@/hooks/useQueries';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '@/lib/api';
import { useAppStore } from '@/stores/useAppStore';
import { EMPTY, int, money, ms, num, ratioAsPct, titleCase } from '@/lib/format';
import type { MLModel } from '@/lib/types';

const FRAMEWORKS = ['vllm', 'tensorrt_llm', 'triton', 'pytorch', 'onnx', 'tensorflow', 'other'];
const QUANTIZATIONS = ['none', 'fp16', 'bf16', 'fp8', 'int8', 'int4', 'awq', 'gptq'];

function RegisterModelForm({ onDone }: { onDone: () => void }) {
  const dataSource = useAppStore((state) => state.dataSource);
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const form = new FormData(event.currentTarget);
    const body: Record<string, unknown> = {
      name: String(form.get('name') ?? '').trim(),
      version: String(form.get('version') ?? '1.0.0').trim(),
      framework: String(form.get('framework') ?? 'vllm'),
      quantization: String(form.get('quantization') ?? 'fp16'),
    };
    const numeric: Array<[string, FormDataEntryValue | null]> = [
      ['parameter_count_b', form.get('parameter_count_b')],
      ['context_length', form.get('context_length')],
      ['max_batch_size', form.get('max_batch_size')],
    ];
    for (const [key, raw] of numeric) {
      const value = String(raw ?? '').trim();
      if (value) body[key] = Number(value);
    }
    const description = String(form.get('description') ?? '').trim();
    if (description) body.description = description;

    try {
      await api.post('/api/v1/models', body, { source: dataSource });
      await client.invalidateQueries({ queryKey: ['models', dataSource] });
      onDone();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Registration failed.');
    } finally {
      setSubmitting(false);
    }
  }

  const inputClass =
    'w-full rounded border border-line-strong bg-elevated px-2 py-1.5 text-xs text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-nvidia';

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Name</span>
          <input name="name" required maxLength={200} className={inputClass} placeholder="llama-3.1-8b-instruct" />
        </label>
        <label className="block">
          <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Version</span>
          <input name="version" defaultValue="1.0.0" maxLength={60} className={inputClass} />
        </label>
        <label className="block">
          <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Framework</span>
          <select name="framework" defaultValue="vllm" className={inputClass}>
            {FRAMEWORKS.map((item) => (
              <option key={item} value={item}>
                {titleCase(item)}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Quantization</span>
          <select name="quantization" defaultValue="fp16" className={inputClass}>
            {QUANTIZATIONS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Parameters (B)</span>
          <input name="parameter_count_b" type="number" step="0.1" min="0" className={inputClass} placeholder="8" />
        </label>
        <label className="block">
          <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Context length</span>
          <input name="context_length" type="number" min="1" className={inputClass} placeholder="131072" />
        </label>
        <label className="block">
          <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Max batch size</span>
          <input name="max_batch_size" type="number" min="1" className={inputClass} placeholder="32" />
        </label>
        <label className="block sm:col-span-2">
          <span className="mb-1 block text-2xs uppercase tracking-wide text-ink-faint">Description</span>
          <input name="description" maxLength={4000} className={inputClass} />
        </label>
      </div>

      {error ? (
        <p role="alert" className="rounded border border-severity-critical/30 bg-severity-critical/5 px-2.5 py-2 text-xs text-severity-critical">
          {error}
        </p>
      ) : null}

      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? 'Registering…' : 'Register model'}
        </Button>
        <Button type="button" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function ModelDetail({ model }: { model: MLModel }) {
  const performance = useModelPerformance(model.id);
  const p = performance.data;

  return (
    <Card>
      <CardHeader
        title={model.display_name ?? model.name}
        description={`${model.name} · v${model.version}`}
        actions={<Badge variant="accent">{model.framework}</Badge>}
      />
      <CardBody>
        <dl className="grid grid-cols-2 gap-y-1.5 text-xs sm:grid-cols-4">
          <dt className="text-ink-faint">Quantization</dt>
          <dd className="text-ink">{model.quantization}</dd>
          <dt className="text-ink-faint">Parameters</dt>
          <dd className="text-ink">{model.parameter_count_b ? `${model.parameter_count_b}B` : EMPTY}</dd>
          <dt className="text-ink-faint">Context</dt>
          <dd className="text-ink">{int(model.context_length)}</dd>
          <dt className="text-ink-faint">Max batch</dt>
          <dd className="text-ink">{int(model.max_batch_size)}</dd>
        </dl>

        {model.description ? (
          <p className="mt-3 text-xs text-ink-muted">{model.description}</p>
        ) : null}

        <div className="mt-4 border-t border-line pt-3">
          <p className="mb-2 text-2xs uppercase tracking-wide text-ink-faint">
            Measured performance in the selected window
          </p>
          {performance.isLoading ? (
            <LoadingState rows={2} />
          ) : performance.isError ? (
            <ErrorState error={performance.error} onRetry={() => void performance.refetch()} compact />
          ) : !p || !p.has_data ? (
            <EmptyState
              title="No traffic recorded for this model"
              description="Performance figures appear once the gateway records requests for it."
            />
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                { label: 'Requests', value: int(p.request_count) },
                { label: 'Avg latency', value: ms(p.avg_latency_ms) },
                { label: 'P95', value: ms(p.p95_latency_ms) },
                { label: 'P99', value: ms(p.p99_latency_ms) },
                { label: 'Throughput', value: `${num(p.throughput_rps, 2)} req/s` },
                { label: 'Tokens/sec', value: num(p.tokens_per_second, 0) },
                { label: 'Avg batch', value: num(p.avg_batch_size, 2) },
                { label: 'Batch eff.', value: p.batch_efficiency !== null ? ratioAsPct(p.batch_efficiency) : EMPTY },
                { label: 'GPU util', value: p.avg_gpu_utilization !== null ? `${num(p.avg_gpu_utilization, 1)}%` : EMPTY },
                { label: 'VRAM', value: p.avg_vram_used_mb !== null ? `${num(p.avg_vram_used_mb / 1024, 1)} GB` : EMPTY },
                { label: 'Error rate', value: p.error_rate !== null ? ratioAsPct(p.error_rate, 2) : EMPTY },
                { label: 'Cost/request', value: money(p.cost_per_request) },
              ].map((item) => (
                <div key={item.label} className="rounded border border-line bg-elevated px-2.5 py-2">
                  <p className="text-2xs uppercase tracking-wide text-ink-faint">{item.label}</p>
                  <p className="mt-0.5 font-mono text-sm tabular-nums text-ink">{item.value}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardBody>
    </Card>
  );
}

export default function ModelsPage() {
  const models = useModels();
  const deployments = useDeployments();
  const [showForm, setShowForm] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const items = models.data?.items ?? [];
  const selected = items.find((model) => model.id === selectedId) ?? items[0];

  return (
    <PageShell
      title="Model Observatory"
      description="Registered model profiles, their deployments and measured performance."
      actions={
        <Button variant="primary" onClick={() => setShowForm((value) => !value)}>
          {showForm ? 'Close' : 'Register model'}
        </Button>
      }
    >
      {showForm ? (
        <Card>
          <CardHeader title="Register a model" description="Adds a profile to the active data source." />
          <CardBody>
            <RegisterModelForm onDone={() => setShowForm(false)} />
          </CardBody>
        </Card>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-1">
          <CardHeader title="Models" description={`${items.length} registered`} />
          <CardBody className="p-0">
            {models.isLoading ? (
              <LoadingState rows={4} />
            ) : models.isError ? (
              <div className="p-4">
                <ErrorState error={models.error} onRetry={() => void models.refetch()} compact />
              </div>
            ) : items.length === 0 ? (
              <EmptyState
                title="No models registered"
                description="Register a model to begin tracking its performance."
                action={
                  <Button variant="primary" onClick={() => setShowForm(true)}>
                    Register model
                  </Button>
                }
              />
            ) : (
              <ul className="divide-y divide-line">
                {items.map((model) => {
                  const isActive = selected?.id === model.id;
                  return (
                    <li key={model.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedId(model.id)}
                        aria-current={isActive ? 'true' : undefined}
                        className={`flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left transition-colors ${
                          isActive ? 'bg-nvidia-faint' : 'hover:bg-elevated'
                        }`}
                      >
                        <div className="min-w-0">
                          <p className={`truncate text-xs ${isActive ? 'text-nvidia' : 'text-ink'}`}>
                            {model.name}
                          </p>
                          <p className="text-2xs text-ink-faint">
                            v{model.version} · {model.quantization}
                            {model.parameter_count_b ? ` · ${model.parameter_count_b}B` : ''}
                          </p>
                        </div>
                        <Badge variant="outline">{model.framework}</Badge>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardBody>
        </Card>

        <div className="space-y-4 xl:col-span-2">
          {selected ? <ModelDetail model={selected} /> : null}

          <Card>
            <CardHeader title="Deployments" description="Where these models are running." />
            <CardBody className="p-0">
              {deployments.isLoading ? (
                <LoadingState rows={3} />
              ) : deployments.isError ? (
                <div className="p-4">
                  <ErrorState error={deployments.error} onRetry={() => void deployments.refetch()} compact />
                </div>
              ) : !deployments.data || deployments.data.length === 0 ? (
                <EmptyState title="No deployments registered" />
              ) : (
                <Table>
                  <THead>
                    <TR>
                      <TH>Name</TH>
                      <TH>Environment</TH>
                      <TH>Backend</TH>
                      <TH align="right">GPUs</TH>
                      <TH align="right">Replicas</TH>
                      <TH align="right">Max batch</TH>
                      <TH align="right">Window</TH>
                      <TH>Status</TH>
                    </TR>
                  </THead>
                  <tbody>
                    {deployments.data.map((deployment) => (
                      <TR key={deployment.id}>
                        <TD>{deployment.name}</TD>
                        <TD>{deployment.environment}</TD>
                        <TD>{deployment.backend}</TD>
                        <TD align="right" mono>{deployment.gpu_count}</TD>
                        <TD align="right" mono>{deployment.replicas}</TD>
                        <TD align="right" mono>{int(deployment.max_batch_size)}</TD>
                        <TD align="right" mono>{ms(deployment.batch_window_ms)}</TD>
                        <TD>
                          <Badge variant={deployment.status === 'active' ? 'accent' : 'default'}>
                            {deployment.status}
                          </Badge>
                        </TD>
                      </TR>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </PageShell>
  );
}
