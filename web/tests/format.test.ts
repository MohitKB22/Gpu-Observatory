import { describe, expect, it } from 'vitest';
import {
  EMPTY,
  bytesFromMb,
  celsius,
  duration,
  int,
  money,
  ms,
  num,
  pct,
  ratioAsPct,
  relativeTime,
  severityClasses,
  titleCase,
} from '@/lib/format';

describe('formatters', () => {
  it('renders null as an em dash, never as zero', () => {
    // A missing measurement must be visually distinct from a measured zero.
    expect(num(null)).toBe(EMPTY);
    expect(int(null)).toBe(EMPTY);
    expect(pct(null)).toBe(EMPTY);
    expect(ms(null)).toBe(EMPTY);
    expect(money(null)).toBe(EMPTY);
    expect(bytesFromMb(null)).toBe(EMPTY);
    expect(celsius(null)).toBe(EMPTY);

    expect(num(0)).not.toBe(EMPTY);
    expect(pct(0)).toBe('0.0%');
  });

  it('formats latency with a unit switch at one second', () => {
    expect(ms(250)).toBe('250.0 ms');
    expect(ms(1500)).toBe('1.50 s');
  });

  it('formats memory with a unit switch at one gigabyte', () => {
    expect(bytesFromMb(512)).toBe('512 MB');
    expect(bytesFromMb(2048)).toBe('2.0 GB');
  });

  it('converts ratios to percentages', () => {
    expect(ratioAsPct(0.0725, 2)).toBe('7.25%');
  });

  it('formats durations', () => {
    expect(duration(45)).toBe('45s');
    expect(duration(125)).toBe('2m 5s');
    expect(duration(7200)).toBe('2h 0m');
  });

  it('titlecases identifiers', () => {
    expect(titleCase('under_batching')).toBe('Under Batching');
    expect(titleCase('gpu_utilization_below')).toBe('Gpu Utilization Below');
  });

  it('produces relative times', () => {
    const now = new Date().toISOString();
    expect(relativeTime(now)).toBe('just now');
    expect(relativeTime(new Date(Date.now() - 120_000).toISOString())).toBe('2m ago');
    expect(relativeTime(null)).toBe(EMPTY);
  });

  it('maps each severity to a distinct class', () => {
    const classes = ['info', 'low', 'medium', 'high', 'critical'].map(severityClasses);
    expect(new Set(classes).size).toBe(5);
  });
});
