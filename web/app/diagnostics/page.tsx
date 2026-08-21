'use client';

import { useState, type FormEvent } from 'react';
import { PageShell } from '@/components/shell/PageShell';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge, SeverityBadge } from '@/components/ui/Badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states/States';
import {
  useAgentCapabilities,
  useAgentChat,
  useAnomalies,
  useDiagnosticsHistory,
  useRunDiagnostics,
} from '@/hooks/useQueries';
import { dateTime, num, relativeTime, titleCase } from '@/lib/format';
import type { Diagnosis } from '@/lib/types';

const SUGGESTIONS = [
  'Why is GPU utilization low?',
  'Why did latency increase?',
  'Which model is fastest?',
  'Which model is cheapest?',
  'Is batching inefficient?',
  'What should I optimize?',
];

function FindingCard({ finding }: { finding: Diagnosis }) {
  return (
    <Card>
      <CardHeader
        title={finding.title}
        description={`${titleCase(finding.kind)} · confidence ${Math.round(finding.confidence * 100)}% · ${relativeTime(finding.generated_at)}`}
        actions={<SeverityBadge severity={finding.severity} />}
      />
      <CardBody className="space-y-3">
        <div>
          <p className="mb-1 text-2xs uppercase tracking-wide text-ink-faint">Root cause</p>
          <p className="text-xs leading-relaxed text-ink">{finding.root_cause}</p>
        </div>

        {finding.evidence.length > 0 ? (
          <div>
            <p className="mb-1 text-2xs uppercase tracking-wide text-ink-faint">Evidence</p>
            <ul className="space-y-1">
              {finding.evidence.map((item) => (
                <li key={item} className="flex gap-2 text-xs text-ink-muted">
                  <span aria-hidden className="text-nvidia">·</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {finding.impact ? (
          <div>
            <p className="mb-1 text-2xs uppercase tracking-wide text-ink-faint">Expected impact</p>
            <p className="text-xs text-ink-muted">{finding.impact}</p>
          </div>
        ) : null}

        {finding.recommendations.length > 0 ? (
          <div>
            <p className="mb-1 text-2xs uppercase tracking-wide text-ink-faint">Recommended actions</p>
            <ol className="space-y-1">
              {finding.recommendations.map((item, index) => (
                <li key={item} className="flex gap-2 text-xs text-ink">
                  <span className="text-ink-faint">{index + 1}.</span>
                  <span>{item}</span>
                </li>
              ))}
            </ol>
          </div>
        ) : null}

        {Object.keys(finding.metrics).length > 0 ? (
          <details className="border-t border-line pt-2">
            <summary className="cursor-pointer text-2xs uppercase tracking-wide text-ink-faint hover:text-ink">
              Metrics this diagnosis fired on
            </summary>
            <dl className="mt-2 grid grid-cols-2 gap-y-1 text-2xs sm:grid-cols-3">
              {Object.entries(finding.metrics)
                .filter(([, value]) => value !== null)
                .map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-2 pr-3">
                    <dt className="truncate text-ink-faint">{key}</dt>
                    <dd className="font-mono tabular-nums text-ink">{String(value)}</dd>
                  </div>
                ))}
            </dl>
          </details>
        ) : null}

        {finding.narrative ? (
          <div className="rounded border border-line bg-elevated p-2.5">
            <p className="mb-1 text-2xs uppercase tracking-wide text-ink-faint">Narrative</p>
            <p className="text-xs text-ink-muted">{finding.narrative}</p>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

export default function DiagnosticsPage() {
  const history = useDiagnosticsHistory();
  const anomalies = useAnomalies();
  const runDiagnostics = useRunDiagnostics();
  const capabilities = useAgentCapabilities();
  const chat = useAgentChat();
  const [question, setQuestion] = useState('');

  function ask(event: FormEvent) {
    event.preventDefault();
    if (question.trim()) chat.mutate(question.trim());
  }

  const findings = runDiagnostics.data?.findings ?? [];
  const historyItems = history.data?.items ?? [];

  return (
    <PageShell
      title="AI Diagnostics"
      description="Deterministic root-cause analysis, with the NVIDIA Performance Copilot for follow-up questions."
      actions={
        <Button
          variant="primary"
          onClick={() => runDiagnostics.mutate()}
          disabled={runDiagnostics.isPending}
        >
          {runDiagnostics.isPending ? 'Analysing…' : 'Run diagnosis'}
        </Button>
      }
    >
      {runDiagnostics.isError ? (
        <ErrorState error={runDiagnostics.error} onRetry={() => runDiagnostics.mutate()} />
      ) : null}

      {runDiagnostics.data ? (
        <div className="flex flex-wrap items-center gap-2 text-2xs text-ink-faint">
          <Badge variant="accent">{runDiagnostics.data.engine}</Badge>
          <span>
            {findings.length} finding{findings.length === 1 ? '' : 's'} over{' '}
            {runDiagnostics.data.analysed_window} · {dateTime(runDiagnostics.data.generated_at)}
          </span>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          {runDiagnostics.isPending ? (
            <LoadingState rows={6} />
          ) : findings.length > 0 ? (
            findings.map((finding, index) => (
              <FindingCard key={`${finding.kind}-${index}`} finding={finding} />
            ))
          ) : historyItems.length > 0 ? (
            <>
              <p className="text-2xs uppercase tracking-wide text-ink-faint">Most recent diagnosis</p>
              <FindingCard finding={historyItems[0]!} />
            </>
          ) : (
            <Card>
              <CardBody>
                <EmptyState
                  title="No diagnosis yet"
                  description="Run a diagnosis to analyse the currently selected time window."
                  action={
                    <Button variant="primary" onClick={() => runDiagnostics.mutate()}>
                      Run diagnosis
                    </Button>
                  }
                />
              </CardBody>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="NVIDIA Performance Copilot"
              description={
                capabilities.data
                  ? capabilities.data.llm_enabled
                    ? `${capabilities.data.provider} · ${capabilities.data.tools.length} read-only tools`
                    : `No language model configured — answers come from the deterministic engine using ${capabilities.data.tools.length} read-only tools.`
                  : undefined
              }
            />
            <CardBody className="space-y-3">
              <form onSubmit={ask} className="space-y-2">
                <label htmlFor="agent-question" className="sr-only">
                  Ask the Performance Copilot
                </label>
                <textarea
                  id="agent-question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  rows={3}
                  maxLength={4000}
                  placeholder="Ask about GPU utilisation, latency, batching or cost…"
                  className="w-full resize-y rounded border border-line-strong bg-elevated px-2.5 py-2 text-xs text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-nvidia"
                />
                <div className="flex flex-wrap gap-1.5">
                  {SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => setQuestion(suggestion)}
                      className="rounded border border-line-strong px-1.5 py-0.5 text-2xs text-ink-muted hover:border-nvidia/50 hover:text-nvidia"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
                <Button type="submit" variant="primary" disabled={chat.isPending || !question.trim()}>
                  {chat.isPending ? 'Thinking…' : 'Ask'}
                </Button>
              </form>

              {chat.isError ? <ErrorState error={chat.error} compact /> : null}

              {chat.data ? (
                <div className="space-y-2 border-t border-line pt-3">
                  <div className="flex items-center gap-2">
                    <Badge variant={chat.data.refused ? 'default' : 'accent'}>
                      {chat.data.refused ? 'refused' : chat.data.engine}
                    </Badge>
                    {!chat.data.refused ? (
                      <span className="text-2xs text-ink-faint">
                        confidence {Math.round(chat.data.confidence * 100)}%
                      </span>
                    ) : null}
                  </div>
                  <div className="whitespace-pre-wrap text-xs leading-relaxed text-ink">
                    {chat.data.answer}
                  </div>
                  {chat.data.tool_calls.length > 0 ? (
                    <details>
                      <summary className="cursor-pointer text-2xs uppercase tracking-wide text-ink-faint hover:text-ink">
                        {chat.data.tool_calls.length} tool call
                        {chat.data.tool_calls.length === 1 ? '' : 's'} behind this answer
                      </summary>
                      <ul className="mt-1.5 space-y-1">
                        {chat.data.tool_calls.map((call, index) => (
                          <li key={`${call.tool}-${index}`} className="text-2xs">
                            <span className={call.ok ? 'text-nvidia' : 'text-severity-critical'}>
                              {call.tool}
                            </span>
                            <span className="text-ink-faint">
                              {call.duration_ms !== null ? ` · ${num(call.duration_ms, 1)} ms` : ''}
                            </span>
                            {call.summary ? (
                              <p className="text-ink-muted">{call.summary}</p>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </div>
              ) : null}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Recent anomalies"
              description="Statistically detected deviations."
            />
            <CardBody className="p-0">
              {anomalies.isLoading ? (
                <LoadingState rows={3} />
              ) : anomalies.isError ? (
                <div className="p-4">
                  <ErrorState error={anomalies.error} onRetry={() => void anomalies.refetch()} compact />
                </div>
              ) : !anomalies.data || anomalies.data.items.length === 0 ? (
                <EmptyState title="No anomalies detected" description="All signals are within their expected range." />
              ) : (
                <ul className="divide-y divide-line">
                  {anomalies.data.items.slice(0, 8).map((anomaly) => (
                    <li key={anomaly.id} className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <SeverityBadge severity={anomaly.severity} />
                        <span className="text-xs text-ink">{titleCase(anomaly.metric_kind)}</span>
                        <span className="ml-auto text-2xs text-ink-faint">
                          {relativeTime(anomaly.detected_at)}
                        </span>
                      </div>
                      {anomaly.description ? (
                        <p className="mt-1 text-2xs text-ink-muted">{anomaly.description}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader title="Diagnosis history" description="Previously recorded findings." />
        <CardBody className="p-0">
          {history.isLoading ? (
            <LoadingState rows={4} />
          ) : history.isError ? (
            <div className="p-4">
              <ErrorState error={history.error} onRetry={() => void history.refetch()} compact />
            </div>
          ) : historyItems.length === 0 ? (
            <EmptyState title="No diagnoses recorded yet" />
          ) : (
            <ul className="divide-y divide-line">
              {historyItems.map((item) => (
                <li key={item.id ?? item.generated_at} className="flex items-start gap-3 px-4 py-2.5">
                  <SeverityBadge severity={item.severity} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs text-ink">{item.title}</p>
                    <p className="text-2xs text-ink-faint">
                      {titleCase(item.kind)} · {item.engine} · confidence{' '}
                      {Math.round(item.confidence * 100)}% · {dateTime(item.generated_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </PageShell>
  );
}
