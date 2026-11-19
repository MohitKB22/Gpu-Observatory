type ValueFormatter = (value: number, name: string) => string;

// Only the parts of Recharts' tooltip props this component reads; Recharts passes more.
interface TooltipEntry {
  name?: unknown;
  value?: unknown;
  color?: string;
  dataKey?: unknown;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: readonly TooltipEntry[];
  label?: string | number;
  formatValue: ValueFormatter;
  formatLabel?: (label: string) => string;
}

export function ChartTooltip({ active, payload, label, formatValue, formatLabel }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-elevated px-3 py-2 text-xs shadow-xl shadow-black/40">
      {label !== undefined && (
        <p className="mb-1.5 font-medium text-fg">{formatLabel ? formatLabel(String(label)) : String(label)}</p>
      )}
      <ul className="space-y-1">
        {payload.map((entry) => (
          <li key={String(entry.dataKey ?? entry.name)} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-muted">
              <span className="size-2 rounded-full" style={{ background: entry.color }} aria-hidden />
              {String(entry.name ?? '')}
            </span>
            <span className="font-mono text-fg tabular-nums">
              {entry.value === null || entry.value === undefined
                ? '—'
                : formatValue(Number(entry.value), String(entry.name))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
