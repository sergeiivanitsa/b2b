import type { StrictJsonInteger } from './strictJson'
import { decimalCoordinate, intervalCoordinates } from './financeGeometry'

function boundedRatio(numerator: bigint, denominator: bigint, size: number): number {
  if (numerator < 0n || denominator < 0n || numerator > denominator) throw new Error('invalid arbitration chart count')
  if (denominator === 0n) return 0
  const precision = 1_000_000_000_000n
  return Number(numerator * precision / denominator) / Number(precision) * size
}

/** Integer arithmetic stays exact until the final bounded SVG coordinate. */
export function arbitrationCountCoordinate(value: StrictJsonInteger, maximum: StrictJsonInteger, size: number): number {
  return boundedRatio(value.value, maximum.value, size)
}

export function arbitrationStackCoordinates(values: readonly StrictJsonInteger[], total: StrictJsonInteger, size: number): readonly (readonly [number, number])[] {
  let cumulative = 0n
  return values.map(value => {
    const start = boundedRatio(cumulative, total.value, size)
    cumulative += value.value
    return [start, boundedRatio(cumulative, total.value, size)] as const
  })
}

export function arbitrationPercentCoordinate(value: string, size: number): number {
  return decimalCoordinate(value, '0', '100', size)
}

export function arbitrationAmountCoordinates(start: string, end: string, minimum: string, maximum: string, size: number): readonly [number, number] {
  if (minimum === '0' && maximum === '0' && start === '0' && end === '0') return [size / 2, size / 2]
  return intervalCoordinates(start, end, minimum, maximum, size)
}
