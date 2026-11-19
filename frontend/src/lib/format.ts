const EM_DASH = '—';

const integerFormat = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const compactFormat = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 });

export function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? EM_DASH : integerFormat.format(value);
}

export function formatCompact(value: number | null | undefined): string {
  return value === null || value === undefined ? EM_DASH : compactFormat.format(value);
}

export function formatDecimal(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return EM_DASH;
  return value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Milliseconds as "840 ms" or "2.41 s". */
export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return EM_DASH;
  if (ms > 0 && ms < 1) return '<1 ms';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
}

/** Ratio 0-1 as a percentage. */
export function formatPercent(ratio: number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined) return EM_DASH;
  return `${(ratio * 100).toFixed(digits)}%`;
}

/** Value already in 0-100. */
export function formatPercentValue(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return EM_DASH;
  return `${value.toFixed(digits)}%`;
}

/** Request rate, switching to per-minute for low-traffic windows so the number stays readable. */
export function formatRequestRate(perSecond: number | null | undefined): string {
  if (perSecond === null || perSecond === undefined) return EM_DASH;
  if (perSecond === 0) return '0 req/s';
  if (perSecond * 60 < 0.1) return `${formatDecimal(perSecond * 3600, 1)} req/h`;
  if (perSecond < 1) return `${formatDecimal(perSecond * 60, perSecond * 60 < 10 ? 2 : 1)} req/min`;
  return `${formatDecimal(perSecond, 2)} req/s`;
}

export function formatTokensPerSecond(value: number | null | undefined): string {
  if (value === null || value === undefined) return EM_DASH;
  return `${formatDecimal(value, value < 10 ? 2 : 1)} tok/s`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return EM_DASH;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatDuration(seconds: number): string {
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${Math.floor(seconds)}s`;
}

export function formatRelativeTime(iso: string | number | null | undefined, now = Date.now()): string {
  if (iso === null || iso === undefined) return 'never';
  const seconds = Math.round((now - new Date(iso).getTime()) / 1000);
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86_400)}d ago`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/** Axis label for a bucket timestamp, coarser for longer windows. */
export function formatBucketTime(iso: string, bucketSeconds: number): string {
  const date = new Date(iso);
  if (bucketSeconds >= 3600) {
    return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', hour12: false });
  }
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

/** Token count with a "~" prefix when it is an estimate. */
export function formatTokens(count: number | null | undefined, source: string | null | undefined): string {
  if (count === null || count === undefined) return EM_DASH;
  return `${source === 'estimated' ? '~' : ''}${formatNumber(count)}`;
}
