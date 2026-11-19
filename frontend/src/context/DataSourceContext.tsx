import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

import { getSystemInfo } from '@/api/endpoints';
import type { DataSource, SystemInfo } from '@/api/types';
import { useApiQuery } from '@/hooks/useApiQuery';

const STORAGE_KEY = 'observatory.dataSource';

interface DataSourceContextValue {
  dataSource: DataSource;
  setDataSource: (value: DataSource) => void;
  systemInfo: SystemInfo | undefined;
  /** False until we know the deployment's default, so pages never briefly mix in demo data. */
  ready: boolean;
}

const DataSourceContext = createContext<DataSourceContextValue | null>(null);

export function DataSourceProvider({ children }: { children: ReactNode }) {
  const systemInfo = useApiQuery(getSystemInfo, []);
  const [chosen, setChosen] = useState<DataSource | null>(readStoredChoice);

  const setDataSource = useCallback((value: DataSource) => {
    setChosen(value);
    try {
      window.localStorage.setItem(STORAGE_KEY, value);
    } catch {
      // Storage can be unavailable (private mode); the choice still applies for this session.
    }
  }, []);

  // If the backend cannot be reached, fall back to real data only rather than guessing.
  const fallback: DataSource = systemInfo.error ? 'real' : 'all';
  const dataSource = chosen ?? systemInfo.data?.default_data_source ?? fallback;
  const ready = chosen !== null || systemInfo.data !== undefined || systemInfo.error !== undefined;

  const value = useMemo(
    () => ({ dataSource, setDataSource, systemInfo: systemInfo.data, ready }),
    [dataSource, setDataSource, systemInfo.data, ready],
  );
  return <DataSourceContext.Provider value={value}>{children}</DataSourceContext.Provider>;
}

export function useDataSource(): DataSourceContextValue {
  const context = useContext(DataSourceContext);
  if (!context) throw new Error('useDataSource must be used inside DataSourceProvider');
  return context;
}

function readStoredChoice(): DataSource | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === 'real' || stored === 'demo' || stored === 'all' ? stored : null;
  } catch {
    return null;
  }
}
