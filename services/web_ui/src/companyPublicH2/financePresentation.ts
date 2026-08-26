import type { PublicH2MoneyDto } from './contractSchema'

/**
 * The server owns money rounding and Russian compact notation.  Decimal ratio
 * leaves are deliberately rendered as their canonical wire strings: a browser
 * must not turn a precise fact into a locale-dependent Number.
 */
export function moneyExact(value: PublicH2MoneyDto): string { return value.display_exact }
export function moneyCompact(value: PublicH2MoneyDto): string { return value.display_compact }
export function percent(value: string | null): string { return value === null ? '—' : `${value} %` }
export function multiple(value: string | null): string { return value === null ? '—' : `${value} ×` }
export function per100(value: string | null): string { return value === null ? '—' : `${value} ₽ из 100 ₽` }
export function year(value: { readonly token: string }): string { return value.token }
export function unavailable(value: string | null | undefined): string { return value ?? '—' }
