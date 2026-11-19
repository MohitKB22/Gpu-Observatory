import { AlertTriangle, Check, Copy } from 'lucide-react';
import { useState, type ReactNode } from 'react';

import { getLog } from '@/api/endpoints';
import type { InferenceRecord } from '@/api/types';
import { DemoBadge, ProviderBadge, TokenSourceBadge } from '@/components/ui/Badge';
import { IconButton } from '@/components/ui/Button';
import { Drawer } from '@/components/ui/Overlay';
import { ErrorState, Spinner } from '@/components/ui/States';
import { RequestStatusBadge } from '@/components/ui/StatusIndicator';
import { useApiQuery } from '@/hooks/useApiQuery';
import { errorTitle } from '@/lib/errors';
import { formatDateTime, formatLatency, formatTokens, formatTokensPerSecond } from '@/lib/format';

export function LogDetailDrawer({ requestId, onClose }: { requestId: string | null; onClose: () => void }) {
  const query = useApiQuery((signal) => getLog(requestId ?? '', signal), [requestId], { enabled: Boolean(requestId) });
  // Only show data for the request currently selected, never a previous one while loading.
  const record = query.data?.id === requestId ? query.data : undefined;

  return (
    <Drawer
      open={Boolean(requestId)}
      onClose={onClose}
      label="Request details"
      title={
        record ? (
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold">{record.model_name}</h2>
              <RequestStatusBadge status={record.status} />
              {record.is_demo && <DemoBadge label={record.source === 'demo_seed' ? 'Demo sample data' : 'Demo'} />}
            </div>
            <p className="text-xs text-muted">{formatDateTime(record.created_at)}</p>
          </div>
        ) : (
          <h2 className="text-base font-semibold">Request details</h2>
        )
      }
    >
      {query.error && !record ? (
        <ErrorState error={query.error} onRetry={query.refetch} />
      ) : !record ? (
        <Spinner label="Loading request" />
      ) : (
        <RecordDetails record={record} />
      )}
    </Drawer>
  );
}

function RecordDetails({ record }: { record: InferenceRecord }) {
  const metrics = record.metrics;
  return (
    <div className="space-y-5">
      {record.is_demo && (
        <p className="rounded-lg border border-secondary/30 bg-secondary/10 px-3 py-2 text-xs text-violet-100">
          {record.source === 'demo_seed'
            ? 'Sample data generated for demo mode. It does not describe a real request.'
            : 'Served by the local demo provider. The response and timing are simulated.'}
        </p>
      )}

      {record.status === 'error' && (
        <section role="alert" className="rounded-lg border border-danger/30 bg-danger/10 p-3">
          <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-red-300">
            <AlertTriangle className="size-4" aria-hidden />
            {errorTitle(record.error_kind)}
            {record.upstream_status_code && <span className="font-mono text-xs">HTTP {record.upstream_status_code}</span>}
          </p>
          <p className="mt-1 text-xs break-words text-red-200">{record.error_message}</p>
        </section>
      )}

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Latency" value={formatLatency(metrics?.latency_ms)} />
        <Stat label="Prompt tokens" value={formatTokens(metrics?.prompt_tokens, metrics?.token_count_source)} />
        <Stat label="Completion tokens" value={formatTokens(metrics?.completion_tokens, metrics?.token_count_source)} />
        <Stat label="Generation speed" value={formatTokensPerSecond(metrics?.tokens_per_second)} />
      </dl>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-xs sm:grid-cols-2">
        <Row label="Request ID">
          <CopyableId value={record.id} />
        </Row>
        <Row label="Provider">
          <ProviderBadge provider={record.provider} />
        </Row>
        <Row label="Temperature">{record.temperature}</Row>
        <Row label="Max tokens">{record.max_tokens}</Row>
        <Row label="Token counts">
          {metrics?.token_count_source ? <TokenSourceBadge source={metrics.token_count_source} /> : 'Not available'}
        </Row>
        <Row label="Source">{record.source}</Row>
        {record.model_id === null && <Row label="Model">Deleted from the registry</Row>}
      </dl>

      {record.system_prompt && <TextBlock title="System prompt">{record.system_prompt}</TextBlock>}
      <TextBlock title="Prompt">{record.prompt}</TextBlock>
      {record.status === 'success' && <TextBlock title="Response">{record.response_text || '(empty response)'}</TextBlock>}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-elevated/40 px-3 py-2">
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-sm font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line/60 py-1.5">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

function TextBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 text-xs font-medium text-muted">{title}</h3>
      <pre className="max-h-80 overflow-auto rounded-lg border border-line bg-canvas p-3 font-mono text-xs leading-relaxed break-words whitespace-pre-wrap">
        {children}
      </pre>
    </section>
  );
}

function CopyableId({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be blocked; the ID is still visible and selectable.
    }
  }
  return (
    <span className="inline-flex items-center gap-1">
      <span className="max-w-40 truncate font-mono" title={value}>
        {value}
      </span>
      <IconButton label={copied ? 'Copied' : 'Copy request ID'} onClick={copy} className="size-6">
        {copied ? <Check className="size-3.5 text-success" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
      </IconButton>
    </span>
  );
}
