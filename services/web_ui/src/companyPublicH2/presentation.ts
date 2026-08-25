import { isStrictJsonInteger, type StrictJsonInteger } from './strictJson'

/** Render only already-validated scalar DTO leaves. */
export function text(value: string | StrictJsonInteger | null | undefined): string {
  if (typeof value === 'string') return value
  return isStrictJsonInteger(value) ? value.token : ''
}
