/** Decimal coordinates are parsed exactly before a bounded final SVG Number. */
type Decimal = Readonly<{ coefficient: bigint; scale: number }>
const DECIMAL = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$/u
function parse(raw: string): Decimal {
  if (!DECIMAL.test(raw)) throw new Error('invalid canonical decimal')
  const negative = raw.startsWith('-'); const body = negative ? raw.slice(1) : raw; const [whole, fraction = ''] = body.split('.')
  return { coefficient: (negative ? -1n : 1n) * BigInt(`${whole}${fraction}`), scale: fraction.length }
}
function scale(value: Decimal, target: number): bigint { return value.coefficient * 10n ** BigInt(target - value.scale) }
function ratio(value: Decimal, min: Decimal, max: Decimal): number {
  const precision = Math.max(value.scale, min.scale, max.scale)
  const denominator = scale(max, precision) - scale(min, precision)
  if (denominator <= 0n) throw new Error('invalid chart axis')
  const numerator = scale(value, precision) - scale(min, precision)
  if (numerator < 0n || numerator > denominator) throw new Error('chart value outside axis')
  // Keep all source arithmetic as bigint.  Only this explicitly bounded
  // 0..1 fixed-point quotient becomes a Number for an SVG coordinate.
  const fixedScale = 1_000_000_000_000n
  return Number(numerator * fixedScale / denominator) / Number(fixedScale)
}
export function decimalCoordinate(value: string, minimum: string, maximum: string, size: number): number { return ratio(parse(value), parse(minimum), parse(maximum)) * size }
export function intervalCoordinates(start: string, end: string, minimum: string, maximum: string, size: number): readonly [number, number] { return [decimalCoordinate(start, minimum, maximum, size), decimalCoordinate(end, minimum, maximum, size)] }
