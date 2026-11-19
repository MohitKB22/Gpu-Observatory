import { useCallback, useEffect, useRef, useState } from 'react';

import { isAbortError } from '@/api/client';

interface QueryOptions {
  /** Poll at this interval while the tab is visible. */
  refreshIntervalMs?: number;
  enabled?: boolean;
}

interface QueryState<T> {
  key?: string;
  data?: T;
  error?: Error;
  updatedAt?: number;
}

export interface QueryResult<T> {
  data: T | undefined;
  error: Error | undefined;
  /** True only before the first successful response. */
  isLoading: boolean;
  /** True whenever a request is in flight, including background refreshes. */
  isFetching: boolean;
  updatedAt: number | undefined;
  refetch: () => void;
}

/**
 * Fetch data for the current `params`, keeping the previous result on screen while new data
 * loads so polling and filter changes never flash an empty page. Requests are aborted when
 * params change or the component unmounts.
 */
export function useApiQuery<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  params: unknown[],
  { refreshIntervalMs, enabled = true }: QueryOptions = {},
): QueryResult<T> {
  const [state, setState] = useState<QueryState<T>>({});
  const [revision, setRevision] = useState(0);
  const fetcherRef = useRef(fetcher);

  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const key = `${JSON.stringify(params)}#${revision}`;

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    fetcherRef
      .current(controller.signal)
      .then((data) => setState({ key, data, updatedAt: Date.now() }))
      .catch((error: unknown) => {
        if (isAbortError(error)) return;
        setState((previous) => ({
          ...previous,
          key,
          error: error instanceof Error ? error : new Error(String(error)),
        }));
      });
    return () => controller.abort();
  }, [key, enabled]);

  useEffect(() => {
    if (!refreshIntervalMs || !enabled) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') setRevision((value) => value + 1);
    }, refreshIntervalMs);
    return () => window.clearInterval(timer);
  }, [refreshIntervalMs, enabled]);

  const refetch = useCallback(() => setRevision((value) => value + 1), []);
  const isFetching = enabled && state.key !== key;

  return {
    data: state.data,
    error: state.error,
    isLoading: isFetching && state.data === undefined && state.error === undefined,
    isFetching,
    updatedAt: state.updatedAt,
    refetch,
  };
}
