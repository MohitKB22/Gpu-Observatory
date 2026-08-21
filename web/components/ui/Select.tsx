'use client';

import type { SelectHTMLAttributes } from 'react';
import { cn } from '@/lib/cn';

interface Option {
  label: string;
  value: string;
}

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'onChange'> {
  label?: string;
  options: Option[];
  value: string;
  onValueChange: (value: string) => void;
}

export function Select({ label, options, value, onValueChange, className, ...rest }: SelectProps) {
  return (
    <label className={cn('flex items-center gap-1.5 text-xs', className)}>
      {label ? <span className="text-ink-faint">{label}</span> : null}
      <select
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        className={cn(
          'rounded border border-line-strong bg-elevated px-2 py-1 text-xs text-ink',
          'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-nvidia',
        )}
        {...rest}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
