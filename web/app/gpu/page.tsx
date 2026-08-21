'use client';

import { useEffect, useMemo } from 'react';
import { PageShell } from '@/components/shell/PageShell';
import { GpuUnavailableNotice } from '@/components/shell/GpuUnavailableNotice';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Select } from '@/components/ui/Select';
import { TimeSeriesChart } from '@/components/charts/TimeSeriesChart';
import { Table, TD, TH, THead, TR } from '@/components/ui/Table';
import { ChartSkeleton, EmptyState, ErrorState, LoadingState } from '@/components/states/States';
import {
  useGpuAvailability,
  useGpuDetail,
  useGpuSeries,
  useGpus,
  useSystemMetrics,
  useSystemSeries,
} from '@/hooks/useQueries';
import { useAppStore } from '@/stores/useAppStore';
import { bytesFromMb, celsius, dateTime, EMPTY, int, num, pct, watts } from '@/lib/format';

function Field({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <>
      <dt className="text-ink-faint">{label}</dt>
      <dd className="truncate font-mono tabular-nums text-ink">{value ?? EMPTY}</dd>
    </>
  );
}

export default function GpuMonitorPage() {
  const gpus = useGpus();
  const availability = useGpuAvailability();
  const { gpuId, setGpuId } = useAppStore();
  const detail = useGpuDetail(gpuId);
  const utilSeries = useGpuSeries('utilization_pct,memory_utilization_pct', gpuId ? [gpuId] : undefined);
  const thermalSeries = useGpuSeries('temperature_c,power_w', gpuId ? [gpuId] : undefined);
  const clockSeries = useGpuSeries('sm_clock_mhz,memory_clock_mhz', gpuId ? [gpuId] : undefined);
  const system = useSystemMetrics();
  const systemSeries = useSystemSeries('cpu_utilization_pct,ram_utilization_pct,disk_utilization_pct');

  // Memoised so the effect below does not re-run on every render.
  const list = useMemo(() => gpus.data ?? [], [gpus.data]);

  // Select the first device once the list arrives, or clear a stale selection.
  useEffect(() => {
    if (list.length === 0) return;
    if (!gpuId || !list.some((gpu) => gpu.id === gpuId)) {
      setGpuId(list[0]!.id);
    }
  }, [list, gpuId, setGpuId]);

  const gpu = detail.data?.gpu;
  const latest = detail.data?.latest;
  const throttles = latest?.throttle_reasons?.split(',').filter(Boolean) ?? [];
  const core = system.data?.latest?.per_core_utilization ?? [];

  return (
    <PageShell
      title="GPU Monitor"
      description="Per-device NVIDIA telemetry, process occupancy and host system metrics."
      actions={
        list.length > 0 ? (
          <Select
            label="Device"
            value={gpuId ?? ''}
            onValueChange={setGpuId}
            options={list.map((item) => ({
              label: `GPU ${item.index} · ${item.name}`,
              value: item.id,
            }))}
          />
        ) : null
      }
    >
      {availability.data ? <GpuUnavailableNotice availability={availability.data} /> : null}

      {gpus.isLoading ? (
        <LoadingState rows={3} />
      ) : gpus.isError ? (
        <ErrorState error={gpus.error} onRetry={() => void gpus.refetch()} />
      ) : list.length === 0 ? (
        <Card>
          <CardBody>
            <EmptyState
              title="No GPUs registered in this data source"
              description="A telemetry agent registers devices on first report. Switch to Demo Mode to explore the interface without NVIDIA hardware."
            />
          </CardBody>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-3">
            <Card>
              <CardHeader title="Device" description={gpu ? gpu.uuid : undefined} />
              <CardBody>
                {detail.isLoading ? (
                  <LoadingState rows={6} />
                ) : detail.isError ? (
                  <ErrorState error={detail.error} onRetry={() => void detail.refetch()} compact />
                ) : gpu ? (
                  <dl className="grid grid-cols-2 gap-y-1.5 text-xs">
                    <Field label="Name" value={gpu.name} />
                    <Field label="Index" value={gpu.index} />
                    <Field label="Host" value={gpu.host} />
                    <Field label="Driver" value={gpu.driver_version} />
                    <Field label="CUDA" value={gpu.cuda_version} />
                    <Field label="VBIOS" value={gpu.vbios_version} />
                    <Field label="Serial" value={gpu.serial} />
                    <Field label="Compute cap." value={gpu.compute_capability} />
                    <Field label="Total VRAM" value={bytesFromMb(gpu.total_memory_mb)} />
                    <Field label="Power limit" value={watts(gpu.power_limit_w)} />
                    <Field label="Max SM clock" value={gpu.max_clock_mhz ? `${gpu.max_clock_mhz} MHz` : EMPTY} />
                    <Field label="Max mem clock" value={gpu.max_memory_clock_mhz ? `${gpu.max_memory_clock_mhz} MHz` : EMPTY} />
                    <Field
                      label="PCIe"
                      value={gpu.pcie_gen ? `Gen ${gpu.pcie_gen} x${gpu.pcie_width ?? '?'}` : EMPTY}
                    />
                    <Field label="Last seen" value={dateTime(gpu.last_seen_at)} />
                  </dl>
                ) : null}
              </CardBody>
            </Card>

            <Card className="xl:col-span-2">
              <CardHeader
                title="Live readings"
                description={
                  detail.data?.freshness.is_stale
                    ? 'Telemetry is stale — the newest sample is older than expected.'
                    : undefined
                }
                actions={
                  throttles.length > 0 ? (
                    <Badge className="border-severity-high/40 bg-severity-high/10 text-severity-high">
                      throttled
                    </Badge>
                  ) : null
                }
              />
              <CardBody>
                {detail.isLoading ? (
                  <LoadingState rows={4} />
                ) : !latest ? (
                  <EmptyState title="No samples for this device yet" />
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      {[
                        { label: 'Utilisation', value: pct(latest.utilization_pct) },
                        { label: 'VRAM', value: pct(latest.memory_utilization_pct) },
                        { label: 'Temperature', value: celsius(latest.temperature_c) },
                        { label: 'Power', value: watts(latest.power_w) },
                        { label: 'VRAM used', value: bytesFromMb(latest.memory_used_mb) },
                        { label: 'VRAM free', value: bytesFromMb(latest.memory_free_mb) },
                        { label: 'SM clock', value: latest.sm_clock_mhz ? `${latest.sm_clock_mhz} MHz` : EMPTY },
                        { label: 'Fan', value: latest.fan_speed_pct !== null ? pct(latest.fan_speed_pct) : 'n/a' },
                      ].map((item) => (
                        <div key={item.label} className="rounded border border-line bg-elevated px-2.5 py-2">
                          <p className="text-2xs uppercase tracking-wide text-ink-faint">{item.label}</p>
                          <p className="mt-0.5 font-mono text-sm tabular-nums text-ink">{item.value}</p>
                        </div>
                      ))}
                    </div>
                    {throttles.length > 0 ? (
                      <p className="mt-3 text-xs text-severity-high">
                        Throttle reasons reported by NVML: {throttles.join(', ')}
                      </p>
                    ) : null}
                    <dl className="mt-3 grid grid-cols-2 gap-y-1.5 text-xs sm:grid-cols-4">
                      <Field label="PCIe TX" value={latest.pcie_tx_kb_s ? `${int(latest.pcie_tx_kb_s)} KB/s` : EMPTY} />
                      <Field label="PCIe RX" value={latest.pcie_rx_kb_s ? `${int(latest.pcie_rx_kb_s)} KB/s` : EMPTY} />
                      <Field label="ECC errors" value={latest.ecc_errors ?? EMPTY} />
                      <Field label="Sampled" value={dateTime(latest.recorded_at)} />
                    </dl>
                  </>
                )}
              </CardBody>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {[
              { title: 'Utilisation and VRAM', query: utilSeries, unit: '%', domain: [0, 100] as [number, number] },
              { title: 'Temperature and power', query: thermalSeries, unit: undefined, domain: undefined },
              { title: 'Clocks', query: clockSeries, unit: 'MHz', domain: undefined },
              { title: 'Host system', query: systemSeries, unit: '%', domain: [0, 100] as [number, number] },
            ].map((panel) => (
              <Card key={panel.title}>
                <CardHeader title={panel.title} />
                <CardBody>
                  {panel.query.isLoading ? (
                    <ChartSkeleton />
                  ) : panel.query.isError ? (
                    <ErrorState error={panel.query.error} onRetry={() => void panel.query.refetch()} compact />
                  ) : !panel.query.data || panel.query.data.series.length === 0 ? (
                    <EmptyState title="No data in this window" />
                  ) : (
                    <TimeSeriesChart
                      series={panel.query.data.series}
                      unit={panel.unit}
                      yDomain={panel.domain}
                    />
                  )}
                </CardBody>
              </Card>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader
                title="Process occupancy"
                description="Processes holding memory on this device."
              />
              <CardBody className="p-0">
                {detail.isLoading ? (
                  <LoadingState rows={3} />
                ) : !detail.data || detail.data.processes.length === 0 ? (
                  <EmptyState
                    title="No process information"
                    description="Per-process GPU accounting requires NVML process APIs, which are unavailable in some virtualised environments."
                  />
                ) : (
                  <Table>
                    <THead>
                      <TR>
                        <TH>PID</TH>
                        <TH>Process</TH>
                        <TH align="right">GPU memory</TH>
                        <TH align="right">SM %</TH>
                        <TH>Workload</TH>
                      </TR>
                    </THead>
                    <tbody>
                      {detail.data.processes.map((process) => (
                        <TR key={process.id}>
                          <TD mono>{process.pid}</TD>
                          <TD>{process.process_name ?? EMPTY}</TD>
                          <TD align="right" mono>
                            {bytesFromMb(process.used_memory_mb)}
                          </TD>
                          <TD align="right" mono>
                            {process.sm_utilization_pct !== null ? pct(process.sm_utilization_pct) : EMPTY}
                          </TD>
                          <TD>{process.workload_label ?? EMPTY}</TD>
                        </TR>
                      ))}
                    </tbody>
                  </Table>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Host system" description="CPU, memory, disk and network." />
              <CardBody>
                {system.isLoading ? (
                  <LoadingState rows={4} />
                ) : system.isError ? (
                  <ErrorState error={system.error} onRetry={() => void system.refetch()} compact />
                ) : !system.data?.latest ? (
                  <EmptyState title="No host telemetry" />
                ) : (
                  <>
                    <dl className="grid grid-cols-2 gap-y-1.5 text-xs sm:grid-cols-3">
                      <Field label="CPU" value={pct(system.data.latest.cpu_utilization_pct)} />
                      <Field label="Cores" value={system.data.latest.core_count} />
                      <Field label="Load 1m" value={num(system.data.latest.load_avg_1m, 2)} />
                      <Field label="RAM" value={pct(system.data.latest.ram_utilization_pct)} />
                      <Field label="RAM used" value={bytesFromMb(system.data.latest.ram_used_mb)} />
                      <Field label="Swap used" value={bytesFromMb(system.data.latest.swap_used_mb)} />
                      <Field label="Disk" value={pct(system.data.latest.disk_utilization_pct)} />
                      <Field label="Net TX" value={`${int(system.data.latest.net_sent_kb_s)} KB/s`} />
                      <Field label="Net RX" value={`${int(system.data.latest.net_recv_kb_s)} KB/s`} />
                      <Field label="Processes" value={int(system.data.latest.process_count)} />
                      <Field label="Host" value={system.data.latest.host} />
                      <Field label="Sampled" value={dateTime(system.data.latest.recorded_at)} />
                    </dl>

                    {core.length > 0 ? (
                      <div className="mt-4">
                        <p className="mb-1.5 text-2xs uppercase tracking-wide text-ink-faint">
                          Per-core utilisation ({core.length} cores)
                        </p>
                        <div className="flex flex-wrap gap-0.5">
                          {core.map((value, index) => (
                            <div
                              key={index}
                              title={`Core ${index}: ${value.toFixed(1)}%`}
                              className="h-4 w-2 rounded-[1px] bg-elevated"
                              style={{
                                background: `linear-gradient(to top, #76b900 ${value}%, #171b19 ${value}%)`,
                              }}
                            />
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </>
                )}
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </PageShell>
  );
}
