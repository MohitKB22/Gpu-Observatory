import { Search, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { listLogs, listModels } from '@/api/endpoints';
import type { DataSource, RequestSource, RequestStatus, TimeWindow } from '@/api/types';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Pagination, RefreshControl } from '@/components/ui/Controls';
import { Input, Select } from '@/components/ui/Form';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { DATA_SOURCES, TIME_WINDOWS } from '@/lib/constants';
import { LogDetailDrawer } from './LogDetailDrawer';
import { LogsTable } from './LogsTable';
import { PAGE_SIZES, useLogFilters } from './useLogFilters';

export default function LogsPage() {
  const { filters, setFilters, clearFilters, selectedRequestId, selectRequest } = useLogFilters();
  const models = useApiQuery(listModels, []);

  // The search box updates immediately; the URL (and the query) follow after a pause in typing.
  const [searchText, setSearchText] = useState(filters.search);
  const debouncedSearch = useDebouncedValue(searchText, 350);
  useEffect(() => {
    if (debouncedSearch !== filters.search) setFilters({ search: debouncedSearch });
    // Only react to the debounced value; filters.search changes as a result of this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  const logs = useApiQuery(
    (signal) =>
      listLogs(
        {
          search: filters.search,
          modelId: filters.modelId,
          status: filters.status,
          source: filters.source,
          dataSource: filters.dataSource,
          window: filters.window,
          page: filters.page,
          pageSize: filters.pageSize,
        },
        signal,
      ),
    [filters.search, filters.modelId, filters.status, filters.source, filters.dataSource, filters.window, filters.page, filters.pageSize],
    { refreshIntervalMs: 30_000 },
  );

  const hasFilters = Boolean(
    filters.search || filters.modelId || filters.status || filters.source || filters.window || filters.dataSource !== 'all',
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Request Logs"
        description="Every recorded inference request, newest first. Select a row for the full prompt, response and error details."
        actions={<RefreshControl updatedAt={logs.updatedAt} isFetching={logs.isFetching} onRefresh={logs.refetch} />}
      />

      <Card className="p-3">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(220px,2fr)_repeat(5,minmax(0,1fr))_auto]">
          <div className="relative sm:col-span-2 lg:col-span-1">
            <label htmlFor="log-search" className="sr-only">
              Search prompts, responses, errors or request ID
            </label>
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" aria-hidden />
            <Input
              id="log-search"
              type="search"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Search prompt, response, error or ID"
              className="pl-9"
              maxLength={200}
            />
          </div>
          <FilterSelect
            id="log-model"
            label="Model"
            value={filters.modelId}
            onChange={(value) => setFilters({ modelId: value })}
            options={[{ value: '', label: 'All models' }, ...(models.data ?? []).map((m) => ({ value: m.id, label: m.name }))]}
          />
          <FilterSelect
            id="log-status"
            label="Status"
            value={filters.status}
            onChange={(value) => setFilters({ status: value as RequestStatus | '' })}
            options={[
              { value: '', label: 'Any status' },
              { value: 'success', label: 'Success' },
              { value: 'error', label: 'Error' },
            ]}
          />
          <FilterSelect
            id="log-source"
            label="Source"
            value={filters.source}
            onChange={(value) => setFilters({ source: value as RequestSource | '' })}
            options={[
              { value: '', label: 'Any source' },
              { value: 'playground', label: 'Playground' },
              { value: 'api', label: 'API' },
              { value: 'demo_seed', label: 'Demo sample data' },
            ]}
          />
          <FilterSelect
            id="log-data"
            label="Data"
            value={filters.dataSource}
            onChange={(value) => setFilters({ dataSource: value as DataSource })}
            options={DATA_SOURCES}
          />
          <FilterSelect
            id="log-window"
            label="Time"
            value={filters.window}
            onChange={(value) => setFilters({ window: value as TimeWindow | '' })}
            options={[{ value: '', label: 'Any time' }, ...TIME_WINDOWS.map((w) => ({ value: w.value, label: `Last ${w.label}` }))]}
          />
          <Button
            variant="ghost"
            disabled={!hasFilters}
            onClick={() => {
              setSearchText('');
              clearFilters();
            }}
            icon={<X className="size-4" aria-hidden />}
          >
            Clear
          </Button>
        </div>
      </Card>

      {logs.error && !logs.data ? (
        <ErrorState error={logs.error} onRetry={logs.refetch} />
      ) : !logs.data ? (
        <Skeleton className="h-96" />
      ) : logs.data.total === 0 ? (
        <Card>
          <EmptyState
            title={hasFilters ? 'No requests match these filters' : 'No requests recorded yet'}
            description={
              hasFilters
                ? 'Try a different search term or clear the filters.'
                : 'Requests appear here as soon as they run, from the Playground or the API.'
            }
          />
        </Card>
      ) : (
        <Card className={logs.isFetching ? 'opacity-80 transition-opacity' : 'transition-opacity'}>
          <LogsTable items={logs.data.items} onSelect={selectRequest} />
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="flex items-center gap-2 text-xs text-muted">
              <label htmlFor="log-page-size">Rows per page</label>
              <Select
                id="log-page-size"
                value={filters.pageSize}
                onChange={(event) => setFilters({ pageSize: Number(event.target.value) })}
                className="h-8 w-20 text-xs"
              >
                {PAGE_SIZES.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </Select>
            </div>
            <Pagination
              page={filters.page}
              pageSize={filters.pageSize}
              total={logs.data.total}
              onPageChange={(page) => setFilters({ page })}
            />
          </div>
        </Card>
      )}

      <LogDetailDrawer requestId={selectedRequestId} onClose={() => selectRequest(null)} />
    </div>
  );
}

interface FilterSelectProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}

function FilterSelect({ id, label, value, onChange, options }: FilterSelectProps) {
  return (
    <div>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <Select id={id} value={value} onChange={(event) => onChange(event.target.value)} className="text-xs">
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </Select>
    </div>
  );
}
