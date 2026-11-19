import type { ModelStatus, RequestStatus } from '@/api/types';
import { cn } from '@/lib/cn';

const MODEL_STATUS: Record<ModelStatus | 'disabled', { label: string; dot: string; text: string }> = {
  healthy: { label: 'Healthy', dot: 'bg-success', text: 'text-green-300' },
  unhealthy: { label: 'Unreachable', dot: 'bg-danger', text: 'text-red-300' },
  unknown: { label: 'Not checked', dot: 'bg-muted', text: 'text-muted' },
  disabled: { label: 'Disabled', dot: 'border border-muted bg-transparent', text: 'text-muted' },
};

/** Connection status: colour plus a text label, never colour alone. */
export function ModelStatusIndicator({ status, enabled = true }: { status: ModelStatus; enabled?: boolean }) {
  const config = MODEL_STATUS[enabled ? status : 'disabled'];
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-xs font-medium whitespace-nowrap', config.text)}>
      <span className={cn('size-2 shrink-0 rounded-full', config.dot)} aria-hidden />
      {config.label}
    </span>
  );
}

export function RequestStatusBadge({ status }: { status: RequestStatus }) {
  const ok = status === 'success';
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[11px] leading-4 font-medium',
        ok ? 'border-success/30 bg-success/10 text-green-300' : 'border-danger/30 bg-danger/10 text-red-300',
      )}
    >
      <span className={cn('size-1.5 rounded-full', ok ? 'bg-success' : 'bg-danger')} aria-hidden />
      {ok ? 'Success' : 'Error'}
    </span>
  );
}
