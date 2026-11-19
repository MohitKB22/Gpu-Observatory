import { twMerge } from 'tailwind-merge';

/** Join class names, skipping falsy values. Later Tailwind classes override conflicting earlier ones,
 * so callers can pass e.g. "w-48" to replace a component's default "w-full". */
export function cn(...classes: (string | false | null | undefined)[]): string {
  return twMerge(classes.filter(Boolean).join(' '));
}
