'use client';

import { create } from 'zustand';
import type { DataSource, RangePreset } from '@/lib/types';

/**
 * Global UI selections shared across screens: time range, data source, GPU and
 * refresh cadence. Kept deliberately small; server data lives in React Query.
 */
interface AppState {
  range: RangePreset;
  dataSource: DataSource;
  gpuId: string | null;
  modelId: string | null;
  refreshMs: number;
  liveEnabled: boolean;
  sidebarOpen: boolean;

  setRange: (range: RangePreset) => void;
  setDataSource: (source: DataSource) => void;
  setGpuId: (id: string | null) => void;
  setModelId: (id: string | null) => void;
  setRefreshMs: (ms: number) => void;
  setLiveEnabled: (enabled: boolean) => void;
  toggleSidebar: () => void;
}

export const RANGE_OPTIONS: RangePreset[] = ['5m', '15m', '1h', '6h', '24h', '7d'];

export const REFRESH_OPTIONS = [
  { label: 'Off', value: 0 },
  { label: '5s', value: 5_000 },
  { label: '10s', value: 10_000 },
  { label: '30s', value: 30_000 },
  { label: '1m', value: 60_000 },
];

export const useAppStore = create<AppState>((set) => ({
  range: '1h',
  dataSource: 'demo',
  gpuId: null,
  modelId: null,
  refreshMs: 10_000,
  liveEnabled: true,
  sidebarOpen: true,

  setRange: (range) => set({ range }),
  setDataSource: (dataSource) => set({ dataSource, gpuId: null, modelId: null }),
  setGpuId: (gpuId) => set({ gpuId }),
  setModelId: (modelId) => set({ modelId }),
  setRefreshMs: (refreshMs) => set({ refreshMs }),
  setLiveEnabled: (liveEnabled) => set({ liveEnabled }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
}));
