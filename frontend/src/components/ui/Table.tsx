import type { HTMLAttributes, ReactNode, TdHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

export function DataTable({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="w-full border-collapse text-left text-sm" aria-label={label}>
        {children}
      </table>
    </div>
  );
}

interface CellProps {
  align?: 'left' | 'right';
  numeric?: boolean;
}

export function Th({ align = 'left', className, children, ...props }: CellProps & HTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn(
        'border-y border-line bg-sidebar/60 px-4 py-2 text-[11px] font-medium tracking-wide whitespace-nowrap text-muted uppercase',
        align === 'right' && 'text-right',
        className,
      )}
      {...props}
    >
      {children}
    </th>
  );
}

export function Td({
  align = 'left',
  numeric,
  className,
  children,
  ...props
}: CellProps & TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={cn(
        'border-b border-line/60 px-4 py-2.5 align-middle',
        align === 'right' && 'text-right',
        numeric && 'font-mono text-xs whitespace-nowrap tabular-nums',
        className,
      )}
      {...props}
    >
      {children}
    </td>
  );
}
