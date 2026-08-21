'use client';

import { Card, CardBody } from '@/components/ui/Card';
import { useAppStore } from '@/stores/useAppStore';
import type { GpuAvailability } from '@/lib/types';

const REASONS: Record<string, string> = {
  nvml_library_not_installed:
    'The NVML library is not installed in this environment, so GPU telemetry cannot be collected.',
  nvml_init_failed:
    'No NVIDIA driver or GPU was detected on this host, so GPU telemetry cannot be collected.',
  no_nvidia_gpu_detected: 'NVML initialised but reported no NVIDIA devices on this host.',
  gpu_metrics_disabled: 'GPU metric collection is disabled by configuration (GPU_METRICS_ENABLED).',
  collector_not_started: 'The telemetry collector has not started yet.',
  demo_mode_synthetic_devices: '',
};

/**
 * States plainly when NVIDIA hardware is unavailable. The platform never
 * fabricates hardware statistics to fill this space.
 */
export function GpuUnavailableNotice({ availability }: { availability: GpuAvailability }) {
  const setDataSource = useAppStore((state) => state.setDataSource);
  if (availability.nvml_available || availability.gpu_count > 0) return null;

  const reason = REASONS[availability.reason ?? ''] ?? 'GPU telemetry is not available.';

  return (
    <Card className="border-severity-medium/40">
      <CardBody>
        <div className="flex items-start gap-3">
          <span aria-hidden className="mt-1 h-2 w-2 shrink-0 rounded-full bg-severity-medium" />
          <div className="space-y-1.5">
            <p className="text-sm font-semibold text-severity-medium">NVIDIA GPU unavailable</p>
            <p className="text-xs text-ink-muted">{reason}</p>
            <p className="text-xs text-ink-faint">
              No hardware statistics are shown because none were measured. To explore the platform
              without NVIDIA hardware, switch to{' '}
              <button
                type="button"
                onClick={() => setDataSource('demo')}
                className="text-nvidia underline underline-offset-2 hover:text-nvidia-bright"
              >
                Demo Mode
              </button>
              .
            </p>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
