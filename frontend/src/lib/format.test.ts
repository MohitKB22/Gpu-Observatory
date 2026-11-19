import { describe, expect, it } from 'vitest';

import {
  formatBytes,
  formatDuration,
  formatLatency,
  formatPercent,
  formatRelativeTime,
  formatRequestRate,
  formatTokens,
} from './format';

describe('formatLatency', () => {
  it.each([
    [null, '—'],
    [0.3, '<1 ms'],
    [840.4, '840 ms'],
    [2410, '2.41 s'],
    [17_532, '17.5 s'],
  ])('%s -> %s', (input, expected) => {
    expect(formatLatency(input)).toBe(expected);
  });
});

describe('formatRequestRate', () => {
  it('switches units so quiet windows stay readable', () => {
    expect(formatRequestRate(0)).toBe('0 req/s');
    expect(formatRequestRate(3)).toBe('3.00 req/s');
    expect(formatRequestRate(0.011)).toBe('0.66 req/min');
    expect(formatRequestRate(0.0001)).toBe('0.4 req/h');
  });
});

describe('formatTokens', () => {
  it('marks estimated counts with a tilde', () => {
    expect(formatTokens(1234, 'estimated')).toBe('~1,234');
    expect(formatTokens(1234, 'exact')).toBe('1,234');
    expect(formatTokens(null, 'exact')).toBe('—');
  });
});

describe('other formatters', () => {
  it('formats percentages, bytes, durations and relative time', () => {
    expect(formatPercent(0.0245)).toBe('2.5%');
    expect(formatPercent(null)).toBe('—');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(8 * 1024 ** 3)).toBe('8.0 GB');
    expect(formatDuration(3 * 3600 + 120)).toBe('3h 2m');
    const now = Date.parse('2026-11-19T12:00:00Z');
    expect(formatRelativeTime('2026-11-19T11:59:30Z', now)).toBe('30s ago');
    expect(formatRelativeTime('2026-11-19T09:00:00Z', now)).toBe('3h ago');
    expect(formatRelativeTime(null, now)).toBe('never');
  });
});
