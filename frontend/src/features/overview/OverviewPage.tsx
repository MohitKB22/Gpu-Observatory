import { Activity, AlertTriangle, Gauge, Zap } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { getOverview } from '@/api/endpoints';
import type { OverviewResponse, TimeWindow } from '@/api/types';
import { TrafficChart } from '@/components/charts/TimeSeriesCharts';
import { PageHeader } from '@/components/layout/PageHeader';
import { Card, CardHeader } from '@/components/ui/Card';
import { RefreshControl, WindowSelector } from '@/components/ui/Controls';
import { StatCard } from '@/components/ui/StatCard';
import { DemoDataNotice, EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { useDataSource } from '@/context/DataSourceContext';
import { useApiQuery } from '@/hooks/useApiQuery';
import { windowLabel } from '@/lib/constants';
import { formatLatency, formatNumber, formatPercent, formatRequestRate, formatTokensPerSecond } from '@/lib/format';
import { ActiveModelsCard } from './ActiveModelsCard';
import { SystemHealthCard } from './SystemHealthCard';

const REFRESH_MS = 15_000;

export default function OverviewPage() {
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('24h');
  const { dataSource, ready } = useDataSource();
  const query = useApiQuery((signal) => getOverview(timeWindow, dataSource, signal), [timeWindow, dataSource], {
    refreshIntervalMs: REFRESH_MS,
    enabled: ready,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description="Serving traffic, latency and health across every registered model."
        actions={
          <>
            <WindowSelector value={timeWindow} onChange={setTimeWindow} />
            <RefreshControl updatedAt={query.updatedAt} isFetching={query.isFetching} onRefresh={query.refetch} />
          </>
        }
      />

      {query.error && !query.data ? (
        <ErrorState error={query.error} onRetry={query.refetch} />
      ) : !query.data ? (
        <OverviewSkeleton />
      ) : (
        <OverviewContent data={query.data} />
      )}
    </div>
  );
}

function OverviewContent({ data }: { data: OverviewResponse }) {
  const { summary, previous_summary: previous } = data;
  const comparison = `vs previous ${data.window}`;
  const hasTraffic = summary.total_requests > 0;

  return (
    <>
      <DemoDataNotice scope={data.scope} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Requests"
          icon={<Activity className="size-4" />}
          value={formatNumber(summary.total_requests)}
          current={summary.total_requests}
          previous={previous.total_requests}
          comparisonLabel={comparison}
          hint={formatRequestRate(summary.requests_per_second)}
        />
        <StatCard
          label="P95 latency"
          icon={<Gauge className="size-4" />}
          value={formatLatency(summary.latency.p95_ms)}
          current={summary.latency.p95_ms}
          previous={previous.latency.p95_ms}
          polarity="lower-is-better"
          comparisonLabel={comparison}
          hint={`P50 ${formatLatency(summary.latency.p50_ms)}`}
        />
        <StatCard
          label="Generation speed"
          icon={<Zap className="size-4" />}
          value={formatTokensPerSecond(summary.avg_tokens_per_second)}
          current={summary.avg_tokens_per_second}
          previous={previous.avg_tokens_per_second}
          polarity="higher-is-better"
          comparisonLabel={comparison}
          hint="mean per request"
        />
        <StatCard
          label="Error rate"
          icon={<AlertTriangle className="size-4" />}
          value={formatPercent(summary.error_rate)}
          current={summary.error_rate}
          previous={previous.error_rate}
          polarity="lower-is-better"
          comparisonLabel={comparison}
          hint={`${formatNumber(summary.error_requests)} failed`}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Traffic and latency"
            description={`Requests per ${bucketLabel(data.bucket_seconds)} with P95 latency, ${windowLabel(data.window)}`}
          />
          <div className="px-2 pb-3">
            {hasTraffic ? (
              <TrafficChart points={data.timeseries} bucketSeconds={data.bucket_seconds} />
            ) : (
              <EmptyState
                title="No requests in this window"
                description="Run a prompt in the Playground or send traffic through the API to see it here."
                action={
                  <Link to="/playground" className="text-xs font-medium text-blue-300 hover:underline">
                    Open the Playground
                  </Link>
                }
              />
            )}
          </div>
        </Card>
        <SystemHealthCard system={data.system} />
      </div>

      <ActiveModelsCard models={data.models} timeWindow={data.window} />
    </>
  );
}

function bucketLabel(seconds: number): string {
  if (seconds >= 3600) return `${seconds / 3600}h`;
  return `${seconds / 60} min`;
}

function OverviewSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading overview">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-28" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Skeleton className="h-80 xl:col-span-2" />
        <Skeleton className="h-80" />
      </div>
    </div>
  );
}
