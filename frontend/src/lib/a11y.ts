/** aria-describedby value for a control rendered inside <Field>: the error when present, else the hint. */
export function describedBy(id: string, error?: string, hasHint = false): string | undefined {
  if (error) return `${id}-error`;
  return hasHint ? `${id}-hint` : undefined;
}
