import { CircleSlash, Gpu } from 'lucide-react';

import type { GpuInfo } from '@/api/types';
import { Card } from '@/components/ui/Card';
import { ProgressBar } from '@/components/ui/States';
import { formatBytes, formatDecimal, formatPercentValue } from '@/lib/format';

export function GpuSection({ gpu }: { gpu: GpuInfo }) {
  return (
    <section aria-labelledby="gpu-heading" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="gpu-heading" className="text-sm font-semibold">
          GPU
        </h2>
        {gpu.available && (
          <p className="text-xs text-muted">
            via {gpu.source === 'nvml' ? 'NVIDIA NVML' : 'nvidia-smi'}
            {gpu.driver_version ? ` · driver ${gpu.driver_version}` : ''}
          </p>
        )}
      </div>

      {gpu.available ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {gpu.devices.map((device) => {
            const memoryPercent =
              device.memory_used_bytes !== null && device.memory_total_bytes
                ? (device.memory_used_bytes / device.memory_total_bytes) * 100
                : null;
            return (
              <Card key={device.index} className="space-y-3 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-xs text-muted">GPU {device.index}</p>
                    <p className="text-sm font-medium">{device.name}</p>
                  </div>
                  <Gpu className="size-4 text-muted" aria-hidden />
                </div>
                <GpuMeter label="Utilisation" value={device.utilization_percent} text={formatPercentValue(device.utilization_percent)} />
                <GpuMeter
                  label="Memory"
                  value={memoryPercent}
                  text={`${formatBytes(device.memory_used_bytes)} / ${formatBytes(device.memory_total_bytes)}`}
                />
                <dl className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <dt className="text-muted">Temperature</dt>
                    <dd className="font-mono tabular-nums">
                      {device.temperature_celsius === null ? 'Not reported' : `${formatDecimal(device.temperature_celsius, 0)} °C`}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted">Power</dt>
                    <dd className="font-mono tabular-nums">
                      {device.power_watts === null ? 'Not reported' : `${formatDecimal(device.power_watts, 0)} W`}
                    </dd>
                  </div>
                </dl>
              </Card>
            );
          })}
        </div>
      ) : (
        <Card className="flex flex-col gap-3 p-5 sm:flex-row sm:items-start">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-full border border-line bg-elevated text-muted">
            <CircleSlash className="size-5" aria-hidden />
          </div>
          <div className="space-y-1.5">
            <p className="text-sm font-medium">GPU telemetry unavailable on the backend host</p>
            <p className="text-xs text-muted">{gpu.unavailable_reason}</p>
            <p className="text-xs text-muted">
              No values are shown rather than estimates. GPU inference can run on a separate server: register it as a
              vLLM model to see its live queue and KV-cache usage below, or run the backend on the GPU machine with the
              NVIDIA Container Toolkit.
            </p>
          </div>
        </Card>
      )}
    </section>
  );
}

function GpuMeter({ label, value, text }: { label: string; value: number | null; text: string }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className="font-mono tabular-nums">{text}</span>
      </div>
      <ProgressBar value={value} label={`GPU ${label.toLowerCase()}`} />
    </div>
  );
}
