'use client';

import { useState } from 'react';
import { PageShell } from '@/components/shell/PageShell';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Table, TD, TH, THead, TR } from '@/components/ui/Table';
import { TimeSeriesChart } from '@/components/charts/TimeSeriesChart';
import { HistogramChart } from '@/components/charts/HistogramChart';
import { ChartSkeleton, EmptyState, ErrorState, LoadingState } from '@/components/states/States';
import {
  useBatchAnalysis,
  useInferenceRequests,
  useInferenceSeries,
  useInferenceSummary,
  useLatencyDistribution,
} from '@/hooks/useQueries';
import { EMPTY, dateTime, int, ms, num, ratioAsPct } from '@/lib/format';

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded border border-line bg-elevated px-2.5 py-2">
      <p className="text-2xs uppercase tracking-wide text-ink-faint">{label}</p>
      <p className="mt-0.5 font-mono text-sm tabular-nums text-ink">{value}</p>
      {hint ? <p className="mt-0.5 text-2xs text-ink-faint">{hint}</p> : null}
    </div>
  );
}

export default function InferencePage() {
  const [errorsOnly, setErrorsOnly] = useState(false);
  const summary = useInferenceSummary();
  const latencySeries = useInferenceSeries('p50_latency_ms,p95_latency_ms,p99_latency_ms');
  const throughputSeries = useInferenceSeries('requests_per_second,tokens_per_second');
  const batchSeries = useInferenceSeries('avg_batch_size,avg_concurrency');
  const distribution = useLatencyDistribution();
  const requests = useInferenceRequests(errorsOnly, 50);
  const batching = useBatchAnalysis();

  const s = summary.data;
  const breakdown = s?.breakdown;
  const total =
    (breakdown?.queue_ms ?? 0) +
    (breakdown?.preprocess_ms ?? 0) +
    (breakdown?.execution_ms ?? 0) +
    (breakdown?.postprocess_ms ?? 0);

  return (
    <PageShell
      title="Inference Performance"
      description="Latency percentiles, throughput, token rates, batching and the request table."
    >
      {summary.isLoading ? (
        <LoadingState rows={3} />
      ) : summary.isError ? (
        <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
      ) : s && s.request_count === 0 ? (
        <Card>
          <CardBody>
            <EmptyState
              title="No inference requests in this window"
              description="Widen the time range, or generate load from the Workloads page."
            />
          </CardBody>
        </Card>
      ) : s ? (
        <>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-6">
            <Stat label="Requests" value={int(s.request_count)} />
            <Stat label="Requests/sec" value={num(s.requests_per_second, 2)} />
            <Stat label="Errors" value={int(s.error_count)} hint={s.error_rate !== null ? ratioAsPct(s.error_rate, 2) : 'not measured'} />
            <Stat label="Avg latency" value={ms(s.latency.avg)} />
            <Stat label="P50" value={ms(s.latency.p50)} />
            <Stat label="P90" value={ms(s.latency.p90)} />
            <Stat label="P95" value={ms(s.latency.p95)} />
            <Stat label="P99" value={ms(s.latency.p99)} />
            <Stat label="Min" value={ms(s.latency.min)} />
            <Stat label="Max" value={ms(s.latency.max)} />
            <Stat label="Tokens/sec" value={num(s.tokens_per_second, 0)} />
            <Stat label="Concurrency" value={num(s.avg_concurrency, 1)} />
            <Stat label="Input tok/s" value={num(s.input_tokens_per_second, 0)} />
            <Stat label="Output tok/s" value={num(s.output_tokens_per_second, 0)} />
            <Stat label="Avg batch" value={num(s.avg_batch_size, 2)} />
            <Stat label="Max batch" value={int(s.max_batch_size)} />
            <Stat label="Input tokens" value={int(s.total_input_tokens)} />
            <Stat label="Output tokens" value={int(s.total_output_tokens)} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader title="Latency percentiles over time" />
              <CardBody>
                {latencySeries.isLoading ? (
                  <ChartSkeleton />
                ) : latencySeries.data && latencySeries.data.series.length > 0 ? (
                  <TimeSeriesChart series={latencySeries.data.series} unit="ms" />
                ) : (
                  <EmptyState title="No latency series in this window" />
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Latency distribution"
                description="Bars are clipped at P99 so a single outlier cannot flatten the histogram; the final bar collects the tail."
              />
              <CardBody>
                {distribution.isLoading ? (
                  <ChartSkeleton />
                ) : distribution.isError ? (
                  <ErrorState error={distribution.error} onRetry={() => void distribution.refetch()} compact />
                ) : !distribution.data || distribution.data.length === 0 ? (
                  <EmptyState title="No requests to plot" />
                ) : (
                  <HistogramChart buckets={distribution.data} />
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Throughput and tokens" />
              <CardBody>
                {throughputSeries.isLoading ? (
                  <ChartSkeleton />
                ) : throughputSeries.data && throughputSeries.data.series.length > 0 ? (
                  <TimeSeriesChart series={throughputSeries.data.series} />
                ) : (
                  <EmptyState title="No throughput series in this window" />
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Batch size and concurrency" />
              <CardBody>
                {batchSeries.isLoading ? (
                  <ChartSkeleton />
                ) : batchSeries.data && batchSeries.data.series.length > 0 ? (
                  <TimeSeriesChart series={batchSeries.data.series} />
                ) : (
                  <EmptyState title="No batching series in this window" />
                )}
              </CardBody>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader
                title="Latency breakdown"
                description="Where request time is actually spent."
              />
              <CardBody>
                {total <= 0 ? (
                  <EmptyState title="No stage timings recorded" />
                ) : (
                  <div className="space-y-2">
                    {[
                      { label: 'Queue', value: breakdown?.queue_ms ?? 0 },
                      { label: 'Preprocess', value: breakdown?.preprocess_ms ?? 0 },
                      { label: 'Execution', value: breakdown?.execution_ms ?? 0 },
                      { label: 'Postprocess', value: breakdown?.postprocess_ms ?? 0 },
                    ].map((stage) => (
                      <div key={stage.label}>
                        <div className="flex items-baseline justify-between text-xs">
                          <span className="text-ink-muted">{stage.label}</span>
                          <span className="font-mono tabular-nums text-ink">
                            {ms(stage.value)} · {((stage.value / total) * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="mt-1 h-1.5 rounded bg-elevated">
                          <div
                            className="h-1.5 rounded bg-nvidia"
                            style={{ width: `${(stage.value / total) * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardBody>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader
                title="Batching analytics"
                description="Effective batch size against the configured maximum."
                actions={
                  batching.data?.under_batching_detected ? (
                    <Badge className="border-severity-high/40 bg-severity-high/10 text-severity-high">
                      under-batching
                    </Badge>
                  ) : batching.data?.over_batching_detected ? (
                    <Badge className="border-severity-medium/40 bg-severity-medium/10 text-severity-medium">
                      over-batching
                    </Badge>
                  ) : null
                }
              />
              <CardBody>
                {batching.isLoading ? (
                  <LoadingState rows={3} />
                ) : batching.isError ? (
                  <ErrorState error={batching.error} onRetry={() => void batching.refetch()} compact />
                ) : !batching.data || batching.data.avg_batch_size === null ? (
                  <EmptyState title="No batching data in this window" />
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <Stat label="Avg batch" value={num(batching.data.avg_batch_size, 2)} />
                      <Stat label="Configured max" value={int(batching.data.configured_max_batch_size)} />
                      <Stat
                        label="Efficiency"
                        value={batching.data.batch_efficiency !== null ? ratioAsPct(batching.data.batch_efficiency, 1) : EMPTY}
                      />
                      <Stat label="Queue depth" value={num(batching.data.avg_queue_depth, 1)} />
                      <Stat label="Formation" value={ms(batching.data.avg_batch_formation_ms)} />
                      <Stat label="GPU util" value={num(batching.data.avg_gpu_utilization, 1)} hint="%" />
                      <Stat label="Throughput" value={num(batching.data.throughput_rps, 2)} hint="req/s" />
                      <Stat
                        label="Headroom"
                        value={batching.data.headroom_pct !== null ? `${num(batching.data.headroom_pct, 0)}%` : EMPTY}
                      />
                    </div>
                    {batching.data.under_batching_detected ? (
                      <p className="mt-3 text-xs text-severity-high">
                        Batches are forming well below the configured maximum while the GPU has
                        spare capacity. Increasing the batching window is usually the highest-value
                        change.
                      </p>
                    ) : null}
                  </>
                )}
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Request performance"
              description="Individual observed requests, newest first."
              actions={
                <Button onClick={() => setErrorsOnly((value) => !value)}>
                  {errorsOnly ? 'Show all' : 'Errors only'}
                </Button>
              }
            />
            <CardBody className="p-0">
              {requests.isLoading ? (
                <LoadingState rows={5} />
              ) : requests.isError ? (
                <div className="p-4">
                  <ErrorState error={requests.error} onRetry={() => void requests.refetch()} compact />
                </div>
              ) : !requests.data || requests.data.items.length === 0 ? (
                <EmptyState
                  title={errorsOnly ? 'No failed requests in this window' : 'No requests in this window'}
                />
              ) : (
                <>
                  <Table>
                    <THead>
                      <TR>
                        <TH>Started</TH>
                        <TH align="right">Total</TH>
                        <TH align="right">Queue</TH>
                        <TH align="right">Execute</TH>
                        <TH align="right">In</TH>
                        <TH align="right">Out</TH>
                        <TH align="right">Batch</TH>
                        <TH align="right">Status</TH>
                      </TR>
                    </THead>
                    <tbody>
                      {requests.data.items.map((row) => (
                        <TR key={row.id} className={row.is_error ? 'bg-severity-critical/5' : undefined}>
                          <TD mono>{dateTime(row.started_at)}</TD>
                          <TD align="right" mono>{ms(row.total_latency_ms)}</TD>
                          <TD align="right" mono>{ms(row.queue_latency_ms)}</TD>
                          <TD align="right" mono>{ms(row.execution_latency_ms)}</TD>
                          <TD align="right" mono>{int(row.input_tokens)}</TD>
                          <TD align="right" mono>{int(row.output_tokens)}</TD>
                          <TD align="right" mono>{int(row.batch_size)}</TD>
                          <TD align="right" mono className={row.is_error ? 'text-severity-critical' : undefined}>
                            {row.status_code}
                          </TD>
                        </TR>
                      ))}
                    </tbody>
                  </Table>
                  <p className="border-t border-line px-3 py-2 text-2xs text-ink-faint">
                    Showing {requests.data.items.length} of {int(requests.data.meta.total)} matching
                    requests.
                  </p>
                </>
              )}
            </CardBody>
          </Card>
        </>
      ) : null}
    </PageShell>
  );
}
