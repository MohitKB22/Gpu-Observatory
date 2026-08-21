'use client';

import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from '@/components/ui/Button';

interface Props {
  children: ReactNode;
  label?: string;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time errors so one broken panel cannot blank the entire
 * dashboard.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Render error', { error, componentStack: info.componentStack });
  }

  private readonly reset = () => this.setState({ error: null });

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        role="alert"
        className="flex flex-col items-start gap-2 rounded border border-severity-high/30 bg-severity-high/5 p-4"
      >
        <p className="text-xs font-semibold text-severity-high">
          {this.props.label ?? 'This panel failed to render'}
        </p>
        <p className="text-xs text-ink-muted">{error.message}</p>
        <Button onClick={this.reset}>Try again</Button>
      </div>
    );
  }
}
