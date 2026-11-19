import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { DataSource, RequestSource, RequestStatus, TimeWindow } from '@/api/types';

export interface LogFilters {
  search: string;
  modelId: string;
  status: RequestStatus | '';
  source: RequestSource | '';
  dataSource: DataSource;
  window: TimeWindow | '';
  page: number;
  pageSize: number;
}

export const PAGE_SIZES = [25, 50, 100];

/** Log filters live in the URL so views can be bookmarked and linked to (e.g. from the Playground). */
export function useLogFilters() {
  const [params, setParams] = useSearchParams();

  const filters: LogFilters = {
    search: params.get('q') ?? '',
    modelId: params.get('model') ?? '',
    status: oneOf(params.get('status'), ['success', 'error'] as const, ''),
    source: oneOf(params.get('source'), ['playground', 'api', 'demo_seed'] as const, ''),
    dataSource: oneOf(params.get('data'), ['all', 'real', 'demo'] as const, 'all'),
    window: oneOf(params.get('window'), ['1h', '6h', '24h', '7d'] as const, ''),
    page: Math.max(1, Number(params.get('page')) || 1),
    pageSize: PAGE_SIZES.includes(Number(params.get('size'))) ? Number(params.get('size')) : PAGE_SIZES[0],
  };
  const selectedRequestId = params.get('request');

  /** Update filters; any change other than the page itself goes back to page 1. */
  const setFilters = useCallback(
    (changes: Partial<LogFilters>) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          const apply = (key: string, value: string | number | undefined) => {
            if (value === undefined) return;
            if (value === '') next.delete(key);
            else next.set(key, String(value));
          };
          apply('q', changes.search);
          apply('model', changes.modelId);
          apply('status', changes.status);
          apply('source', changes.source);
          apply('data', changes.dataSource === 'all' ? '' : changes.dataSource);
          apply('window', changes.window);
          apply('size', changes.pageSize);
          if (changes.page !== undefined) apply('page', changes.page > 1 ? changes.page : '');
          else next.delete('page');
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const selectRequest = useCallback(
    (id: string | null) => {
      setParams((current) => {
        const next = new URLSearchParams(current);
        if (id) next.set('request', id);
        else next.delete('request');
        return next;
      });
    },
    [setParams],
  );

  const clearFilters = useCallback(() => setParams(new URLSearchParams(), { replace: true }), [setParams]);

  return { filters, setFilters, clearFilters, selectedRequestId, selectRequest };
}

function oneOf<T extends string, F extends string>(value: string | null, allowed: readonly T[], fallback: F): T | F {
  return allowed.includes(value as T) ? (value as T) : fallback;
}
