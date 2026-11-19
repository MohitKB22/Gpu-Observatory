import { ChevronLeft, ChevronRight, RotateCw } from 'lucide-react';

import type { TimeWindow } from '@/api/types';
import { useNow } from '@/hooks/useNow';
import { TIME_WINDOWS } from '@/lib/constants';
import { formatNumber, formatRelativeTime } from '@/lib/format';
import { cn } from '@/lib/cn';
import { IconButton } from './Button';

interface SegmentedControlProps<T extends string> {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}

export function SegmentedControl<T extends string>({ label, value, options, onChange }: SegmentedControlProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line bg-canvas p-0.5">
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={cn(
              'h-7 cursor-pointer rounded px-2.5 text-xs font-medium transition-colors duration-150',
              selected ? 'bg-elevated text-fg shadow-sm' : 'text-muted hover:text-fg',
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function WindowSelector({ value, onChange }: { value: TimeWindow; onChange: (value: TimeWindow) => void }) {
  return <SegmentedControl label="Time window" value={value} options={TIME_WINDOWS} onChange={onChange} />;
}

interface RefreshControlProps {
  updatedAt: number | undefined;
  isFetching: boolean;
  onRefresh: () => void;
}

export function RefreshControl({ updatedAt, isFetching, onRefresh }: RefreshControlProps) {
  const now = useNow(5000);
  return (
    <div className="flex items-center gap-1 text-xs text-muted">
      <span className="hidden tabular-nums sm:inline" aria-live="off">
        {updatedAt ? `Updated ${formatRelativeTime(updatedAt, now)}` : ''}
      </span>
      <IconButton label="Refresh now" onClick={onRefresh} disabled={isFetching}>
        <RotateCw className={cn('size-4', isFetching && 'animate-spin')} aria-hidden />
      </IconButton>
    </div>
  );
}

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, pageSize, total, onPageChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3 text-xs text-muted">
      <span className="tabular-nums">
        {formatNumber(first)}–{formatNumber(last)} of {formatNumber(total)}
      </span>
      <div className="flex items-center gap-1">
        <IconButton label="Previous page" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          <ChevronLeft className="size-4" aria-hidden />
        </IconButton>
        <span className="px-1 tabular-nums">
          Page {page} of {formatNumber(totalPages)}
        </span>
        <IconButton label="Next page" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
          <ChevronRight className="size-4" aria-hidden />
        </IconButton>
      </div>
    </nav>
  );
}
