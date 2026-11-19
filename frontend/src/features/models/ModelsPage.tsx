import { ChevronDown, ChevronRight, Info, Pencil, PlugZap, Plus, Trash2 } from 'lucide-react';
import { Fragment, useState } from 'react';

import { errorMessage } from '@/api/client';
import { checkModelConnection, deleteModel, listModels, updateModel } from '@/api/endpoints';
import type { Model } from '@/api/types';
import { PageHeader } from '@/components/layout/PageHeader';
import { DemoBadge, ProviderBadge } from '@/components/ui/Badge';
import { Button, IconButton } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { RefreshControl } from '@/components/ui/Controls';
import { Switch } from '@/components/ui/Form';
import { Modal } from '@/components/ui/Overlay';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { ModelStatusIndicator } from '@/components/ui/StatusIndicator';
import { DataTable, Td, Th } from '@/components/ui/Table';
import { useToast } from '@/context/ToastContext';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useNow } from '@/hooks/useNow';
import { formatLatency, formatRelativeTime } from '@/lib/format';
import { HealthHistory } from './HealthHistory';
import { ModelFormModal } from './ModelFormModal';

export default function ModelsPage() {
  const query = useApiQuery(listModels, [], { refreshIntervalMs: 30_000 });
  const { notify } = useToast();
  const now = useNow(10_000);

  const [editing, setEditing] = useState<Model | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [deleting, setDeleting] = useState<Model | null>(null);
  const [deletePending, setDeletePending] = useState(false);
  const [checking, setChecking] = useState<Set<string>>(new Set());
  const [toggling, setToggling] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [historyRevision, setHistoryRevision] = useState(0);

  function openCreate() {
    setEditing(null);
    setFormOpen(true);
  }

  function openEdit(model: Model) {
    setEditing(model);
    setFormOpen(true);
  }

  async function handleCheck(model: Model) {
    setChecking((current) => new Set(current).add(model.id));
    try {
      const result = await checkModelConnection(model.id);
      if (result.check.status === 'healthy') {
        notify({ tone: 'success', title: `${model.name} is reachable`, description: `Responded in ${formatLatency(result.check.latency_ms)}.` });
      } else {
        notify({ tone: 'error', title: `${model.name} failed the check`, description: result.check.error_message ?? undefined });
      }
      setHistoryRevision((value) => value + 1);
      query.refetch();
    } catch (error) {
      notify({ tone: 'error', title: 'Connection check failed', description: errorMessage(error) });
    } finally {
      setChecking((current) => withoutId(current, model.id));
    }
  }

  async function handleToggle(model: Model, enabled: boolean) {
    setToggling((current) => new Set(current).add(model.id));
    try {
      await updateModel(model.id, { is_enabled: enabled });
      notify({ tone: 'success', title: `${model.name} ${enabled ? 'enabled' : 'disabled'} in the Observatory` });
      query.refetch();
    } catch (error) {
      notify({ tone: 'error', title: 'Could not update the model', description: errorMessage(error) });
    } finally {
      setToggling((current) => withoutId(current, model.id));
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    setDeletePending(true);
    try {
      await deleteModel(deleting.id);
      notify({ tone: 'success', title: `${deleting.name} removed from the registry` });
      setDeleting(null);
      query.refetch();
    } catch (error) {
      notify({ tone: 'error', title: 'Could not delete the model', description: errorMessage(error) });
    } finally {
      setDeletePending(false);
    }
  }

  const models = query.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Model Registry"
        description="Register inference endpoints, verify connectivity and control which models receive traffic."
        actions={
          <>
            <RefreshControl updatedAt={query.updatedAt} isFetching={query.isFetching} onRefresh={query.refetch} />
            <Button variant="primary" icon={<Plus className="size-4" aria-hidden />} onClick={openCreate}>
              Register model
            </Button>
          </>
        }
      />

      <p className="flex items-start gap-2 text-xs text-muted">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        Status comes from connection checks (on demand and every minute in the background). Enabling or disabling a
        model only changes whether the Observatory sends it traffic; it never deploys or stops the model itself.
      </p>

      {query.error && !models ? (
        <ErrorState error={query.error} onRetry={query.refetch} />
      ) : !models ? (
        <Skeleton className="h-64" />
      ) : models.length === 0 ? (
        <Card>
          <EmptyState
            icon={<PlugZap className="size-5" aria-hidden />}
            title="No models registered yet"
            description="Connect an OpenAI-compatible API, a vLLM server or a Hugging Face endpoint. Use the demo provider to try the dashboard without credentials."
            action={
              <Button variant="primary" icon={<Plus className="size-4" aria-hidden />} onClick={openCreate}>
                Register model
              </Button>
            }
          />
        </Card>
      ) : (
        <Card>
          <DataTable label="Registered models">
            <thead>
              <tr>
                <Th className="w-8">
                  <span className="sr-only">Expand</span>
                </Th>
                <Th>Model</Th>
                <Th>Provider</Th>
                <Th>Endpoint</Th>
                <Th>Status</Th>
                <Th>Enabled</Th>
                <Th align="right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {models.map((model) => {
                const isExpanded = expanded === model.id;
                return (
                  <Fragment key={model.id}>
                    <tr className="transition-colors hover:bg-elevated/40">
                      <Td className="pr-0">
                        <IconButton
                          label={isExpanded ? `Hide check history for ${model.name}` : `Show check history for ${model.name}`}
                          aria-expanded={isExpanded}
                          onClick={() => setExpanded(isExpanded ? null : model.id)}
                        >
                          {isExpanded ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
                        </IconButton>
                      </Td>
                      <Td>
                        <div className="flex items-center gap-2 font-medium">
                          {model.name}
                          {model.is_demo && <DemoBadge />}
                        </div>
                        <div className="mt-0.5 font-mono text-[11px] text-muted">{model.model_identifier}</div>
                      </Td>
                      <Td>
                        <ProviderBadge provider={model.provider} />
                      </Td>
                      <Td className="max-w-64">
                        {model.endpoint_url ? (
                          <span className="block truncate font-mono text-xs text-muted" title={model.endpoint_url}>
                            {model.endpoint_url}
                          </span>
                        ) : (
                          <span className="text-xs text-muted">In-process</span>
                        )}
                      </Td>
                      <Td>
                        <ModelStatusIndicator status={model.status} />
                        <div className="mt-0.5 text-[11px] text-muted">
                          {model.last_checked_at
                            ? `${formatRelativeTime(model.last_checked_at, now)} · ${formatLatency(model.last_check_latency_ms)}`
                            : 'Never checked'}
                        </div>
                      </Td>
                      <Td>
                        <Switch
                          checked={model.is_enabled}
                          disabled={toggling.has(model.id)}
                          onChange={(enabled) => handleToggle(model, enabled)}
                          label={`${model.is_enabled ? 'Disable' : 'Enable'} ${model.name} in the Observatory`}
                        />
                      </Td>
                      <Td align="right">
                        <div className="flex justify-end gap-1">
                          <Button
                            size="sm"
                            onClick={() => handleCheck(model)}
                            loading={checking.has(model.id)}
                            icon={<PlugZap className="size-3.5" aria-hidden />}
                          >
                            Check connection
                          </Button>
                          <IconButton label={`Edit ${model.name}`} onClick={() => openEdit(model)}>
                            <Pencil className="size-4" aria-hidden />
                          </IconButton>
                          <IconButton
                            label={`Delete ${model.name}`}
                            onClick={() => setDeleting(model)}
                            className="hover:text-red-300"
                          >
                            <Trash2 className="size-4" aria-hidden />
                          </IconButton>
                        </div>
                      </Td>
                    </tr>
                    {isExpanded && (
                      <tr className="bg-sidebar/40">
                        <td colSpan={7} className="border-b border-line/60 px-4 py-3 pl-14">
                          {model.last_error && (
                            <p className="mb-2 text-xs text-red-200">
                              <span className="font-medium text-red-300">Last error:</span> {model.last_error}
                            </p>
                          )}
                          <HealthHistory modelId={model.id} revision={historyRevision} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </DataTable>
        </Card>
      )}

      <ModelFormModal
        open={formOpen}
        model={editing}
        onClose={() => setFormOpen(false)}
        onSaved={(saved, created) => {
          setFormOpen(false);
          notify({ tone: 'success', title: created ? `${saved.name} registered` : `${saved.name} updated` });
          query.refetch();
        }}
      />

      <Modal
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        title={`Delete ${deleting?.name ?? 'model'}?`}
        footer={
          <>
            <Button onClick={() => setDeleting(null)} disabled={deletePending}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleDelete} loading={deletePending}>
              Delete model
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          The model and its connection-check history are removed from the registry. Recorded requests stay in the
          request log under the model's name. Nothing changes on the serving endpoint itself.
        </p>
      </Modal>
    </div>
  );
}

function withoutId(set: Set<string>, id: string): Set<string> {
  const next = new Set(set);
  next.delete(id);
  return next;
}
