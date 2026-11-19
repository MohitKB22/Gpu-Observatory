import { lazy } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AppLayout } from '@/components/layout/AppLayout';
import { DataSourceProvider } from '@/context/DataSourceContext';
import { ToastProvider } from '@/context/ToastContext';

// Each module is its own chunk, so the first page load only downloads what it renders.
const OverviewPage = lazy(() => import('@/features/overview/OverviewPage'));
const ModelsPage = lazy(() => import('@/features/models/ModelsPage'));
const PlaygroundPage = lazy(() => import('@/features/playground/PlaygroundPage'));
const AnalyticsPage = lazy(() => import('@/features/analytics/AnalyticsPage'));
const InfrastructurePage = lazy(() => import('@/features/infrastructure/InfrastructurePage'));
const LogsPage = lazy(() => import('@/features/logs/LogsPage'));

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="models" element={<ModelsPage />} />
        <Route path="playground" element={<PlaygroundPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="infrastructure" element={<InfrastructurePage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <DataSourceProvider>
          <AppRoutes />
        </DataSourceProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
