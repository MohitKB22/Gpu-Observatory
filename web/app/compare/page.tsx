'use client';

import { useMemo, useState } from 'react';
import { PageShell } from '@/components/shell/PageShell';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Table, TD, TH, THead, TR } from '@/components/ui/Table';
import { ComparisonBarChart, type ComparisonRow } from '@/components/charts/ComparisonBarChart';
import { ChartSkeleton, EmptyState, ErrorState, LoadingState } from '@/components/states/States';
import { useComparison, useModels } from '@/hooks/useQueries';
import { EMPTY, money, ms, num, ratioAsPct } from '@/lib/format';
import { cn } from '@/lib/cn';

const ROWS: Array<{
  key: keyof import('@/lib/types').ModelPerformance;
  label: string;
  format: (value: number | null) => string;
  lowerIsBetter: boolean;
}> = [
  { key: 'avg_latency_ms', label: 'Average latency', format: (v) => ms(v), lowerIsBetter: true },
  { key: 'p95_latency_ms', label: 'P95 latency', format: (v) => ms(v), lowerIsBetter: true },
  { key: 'p99_latency_ms', label: 'P99 latency', format: (v) => ms(v), lowerIsBetter: true },
  { key: 'throughput_rps', label: 'Throughput (req/s)', format: (v) => num(v, 3), lowerIsBetter: false },
  { key: 'tokens_per_second', label: 'Tokens/sec', format: (v) => num(v, 0), lowerIsBetter: false },
  { key: 'avg_batch_size', label: 'Average batch size', format: (v) => num(v, 2), lowerIsBetter: false },
  { key: 'batch_efficiency', label: 'Batch efficiency', format: (v) => (v === null ? EMPTY : ratioAsPct(v)), lowerIsBetter: false },
  { key: 'avg_gpu_utilization', label: 'GPU utilisation (%)', format: (v) => num(v, 1), lowerIsBetter: false },
  { key: 'avg_vram_used_mb', label: 'VRAM used (MB)', format: (v) => num(v, 0), lowerIsBetter: true },
  { key: 'error_rate', label: 'Error rate', format: (v) => (v === null ? EMPTY : ratioAsPct(v, 2)), lowerIsBetter: true },
  { key: 'cost_per_request', label: 'Cost per request', format: (v) => money(v), lowerIsBetter: true },
  { key: 'cost_per_1m_tokens', label: 'Cost per 1M tokens', format: (v) => money(v), lowerIsBetter: true },
];

export default function ComparePage() {
  const models = useModels();
  const [selected, setSelected] = useState<string[]>([]);
  const items = useMemo(() => models.data?.items ?? [], [models.data]);

  const effective = useMemo(() => {
    if (selected.length >= 2) return selected;
    return items.slice(0, 2).map((model) => model.id);
  }, [selected, items]);

  const comparison = useComparison(effective);

  function toggle(id: string) {
    setSelected((current) => {
      const base = current.length >= 2 ? current : effective;
      if (base.includes(id)) {
        const next = base.filter((item) => item !== id);
        return next;
      }
      if (base.length >= 6) return base;
      return [...base, id];
    });
  }

  const performances = useMemo(() => comparison.data?.models ?? [], [comparison.data]);

  const chartRows: ComparisonRow[] = useMemo(() => {
    if (performances.length === 0) return [];
    const metrics: Array<[string, keyof import('@/lib/types').ModelPerformance]> = [
      ['P95 latency (ms)', 'p95_latency_ms'],
      ['Throughput (req/s)', 'throughput_rps'],
      ['Batch size', 'avg_batch_size'],
      ['GPU util (%)', 'avg_gpu_utilization'],
    ];
    return metrics.map(([label, key]) => {
      const row: ComparisonRow = { metric: label };
      for (const performance of performances) {
        row[performance.model_name] = Number(performance[key] ?? 0);
      }
      return row;
    });
  }, [performances]);

  return (
    <PageShell
      title="Model Comparison"
      description="Side-by-side comparison computed from stored metrics. Select two to six models."
    >
      <Card>
        <CardHeader title="Select models" description="The first selection is treated as the baseline." />
        <CardBody>
          {models.isLoading ? (
            <LoadingState rows={2} />
          ) : models.isError ? (
            <ErrorState error={models.error} onRetry={() => void models.refetch()} compact />
          ) : items.length < 2 ? (
            <EmptyState
              title="At least two models are needed"
              description="Register more models, or switch data source, to run a comparison."
            />
          ) : (
            <div className="flex flex-wrap gap-2">
              {items.map((model) => {
                const isSelected = effective.includes(model.id);
                return (
                  <button
                    key={model.id}
                    type="button"
                    onClick={() => toggle(model.id)}
                    aria-pressed={isSelected}
                    className={cn(
                      'rounded border px-2.5 py-1.5 text-xs transition-colors',
                      isSelected
                        ? 'border-nvidia bg-nvidia-faint text-nvidia'
                        : 'border-line-strong bg-elevated text-ink-muted hover:text-ink',
                    )}
                  >
                    {model.name}
                    <span className="ml-1.5 text-2xs opacity-70">v{model.version}</span>
                  </button>
                );
              })}
            </div>
          )}
        </CardBody>
      </Card>

      {comparison.isError ? (
        <ErrorState error={comparison.error} onRetry={() => void comparison.refetch()} />
      ) : null}

      {comparison.data ? (
        <>
          <Card>
            <CardHeader
              title="Recommendation"
              description="Computed arithmetically from the measured metrics — no language model is involved."
            />
            <CardBody>
              {comparison.data.recommendation ? (
                <div className="space-y-2">
                  <p className="text-sm text-ink">{comparison.data.recommendation}</p>
                  {comparison.data.confidence !== null ? (
                    <p className="text-2xs text-ink-faint">
                      Confidence {Math.round(comparison.data.confidence * 100)}% · window{' '}
                      {comparison.data.range_label}
                    </p>
                  ) : null}
                </div>
              ) : (
                <p className="text-xs text-ink-muted">
                  Not enough measured data to make a recommendation.
                </p>
              )}
              {comparison.data.caveats.length > 0 ? (
                <ul className="mt-3 space-y-1 border-t border-line pt-3">
                  {comparison.data.caveats.map((caveat) => (
                    <li key={caveat} className="flex gap-2 text-2xs text-severity-medium">
                      <span aria-hidden>!</span>
                      <span>{caveat}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Metric comparison" />
            <CardBody className="p-0">
              <Table>
                <THead>
                  <TR>
                    <TH>Metric</TH>
                    {performances.map((performance, index) => (
                      <TH key={performance.model_id} align="right">
                        <span className="block truncate">{performance.model_name}</span>
                        <span className="block text-[9px] font-normal normal-case text-ink-faint">
                          {index === 0 ? 'baseline' : `v${performance.version}`}
                          {comparison.data?.recommended_model_id === performance.model_id
                            ? ' · recommended'
                            : ''}
                        </span>
                      </TH>
                    ))}
                  </TR>
                </THead>
                <tbody>
                  {ROWS.map((row) => {
                    const values = performances.map((p) => p[row.key] as number | null);
                    const defined = values.filter((v): v is number => v !== null);
                    const best = defined.length
                      ? row.lowerIsBetter
                        ? Math.min(...defined)
                        : Math.max(...defined)
                      : null;
                    return (
                      <TR key={String(row.key)}>
                        <TD className="text-ink-muted">{row.label}</TD>
                        {values.map((value, index) => (
                          <TD
                            key={`${String(row.key)}-${index}`}
                            align="right"
                            mono
                            className={cn(
                              best !== null && value === best && defined.length > 1 && 'text-nvidia',
                            )}
                          >
                            {row.format(value)}
                          </TD>
                        ))}
                      </TR>
                    );
                  })}
                  <TR>
                    <TD className="text-ink-muted">Requests observed</TD>
                    {performances.map((performance) => (
                      <TD key={`count-${performance.model_id}`} align="right" mono>
                        {num(performance.request_count, 0)}
                      </TD>
                    ))}
                  </TR>
                </tbody>
              </Table>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Visual comparison" />
            <CardBody>
              {comparison.isLoading ? (
                <ChartSkeleton height={260} />
              ) : chartRows.length === 0 ? (
                <EmptyState title="No comparable metrics" />
              ) : (
                <ComparisonBarChart
                  rows={chartRows}
                  models={performances.map((performance) => performance.model_name)}
                />
              )}
            </CardBody>
          </Card>

          {performances.some((performance) => !performance.has_data) ? (
            <Card className="border-severity-medium/40">
              <CardBody>
                <p className="text-xs text-severity-medium">
                  {performances
                    .filter((performance) => !performance.has_data)
                    .map((performance) => performance.model_name)
                    .join(', ')}{' '}
                  had no recorded traffic in this window, so their columns are empty rather than
                  estimated.
                </p>
              </CardBody>
            </Card>
          ) : null}
        </>
      ) : comparison.isLoading && effective.length >= 2 ? (
        <LoadingState rows={5} />
      ) : null}

      <div className="flex items-center gap-2 text-2xs text-ink-faint">
        <Badge variant="outline">note</Badge>
        <span>
          Highlighted values are the best in each row. Cost figures are estimates from the active
          pricing profile.
        </span>
      </div>
    </PageShell>
  );
}
