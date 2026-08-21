import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import './globals.css';
import { Providers } from './providers';
import { AppFrame } from '@/components/shell/AppFrame';

export const metadata: Metadata = {
  title: 'NVIDIA AI Performance Observatory',
  description:
    'Observability and performance optimisation for NVIDIA AI inference workloads: GPU telemetry, inference performance, batching analytics, cost and AI-assisted root-cause diagnosis.',
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: '#0a0c0b',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <Providers>
          <AppFrame>{children}</AppFrame>
        </Providers>
      </body>
    </html>
  );
}
