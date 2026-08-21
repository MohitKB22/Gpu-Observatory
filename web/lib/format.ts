/** Display formatting helpers.
 *
 * Everything here renders `null` as an explicit em dash rather than `0`, so a
 * missing measurement is never mistaken for a measured zero.
 */

export const EMPTY = '—';

export function num(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function int(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  return Math.round(value).toLocaleString();
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  return `${num(value, digits)}%`;
}

export function ratioAsPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  return `${num(value * 100, digits)}%`;
}

export function ms(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  if (value >= 1000) return `${num(value / 1000, 2)} s`;
  return `${num(value, digits)} ms`;
}

export function bytesFromMb(mb: number | null | undefined): string {
  if (mb === null || mb === undefined || Number.isNaN(mb)) return EMPTY;
  if (mb >= 1024) return `${num(mb / 1024, 1)} GB`;
  return `${num(mb, 0)} MB`;
}

export function watts(value: number | null | undefined): string {
  if (value === null || value === undefined) return EMPTY;
  return `${num(value, 0)} W`;
}

export function celsius(value: number | null | undefined): string {
  if (value === null || value === undefined) return EMPTY;
  return `${num(value, 1)} °C`;
}

export function money(value: number | null | undefined, currency = 'USD'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  const digits = Math.abs(value) < 0.01 && value !== 0 ? 6 : 2;
  try {
    return value.toLocaleString(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  } catch {
    return `${currency} ${num(value, digits)}`;
  }
}

export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  return Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(
    value,
  );
}

export function timeOfDay(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return EMPTY;
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return EMPTY;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${Math.round(seconds % 60)}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
    .trim();
}

/** Colour class for a severity level. */
export function severityClasses(severity: string): string {
  switch (severity) {
    case 'critical':
      return 'text-severity-critical border-severity-critical/40 bg-severity-critical/10';
    case 'high':
      return 'text-severity-high border-severity-high/40 bg-severity-high/10';
    case 'medium':
      return 'text-severity-medium border-severity-medium/40 bg-severity-medium/10';
    case 'low':
      return 'text-severity-low border-severity-low/40 bg-severity-low/10';
    default:
      return 'text-severity-info border-severity-info/40 bg-severity-info/10';
  }
}
