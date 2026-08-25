import { canonicalFullProjectionBytes, canonicalJsonBytes, canonicalProjectionDigest } from './canonicalJson'
import { CompanyPublicH2ContractError } from './contractErrors'
import { object, type CompanyPublicH2, validateCompanyPublicH2Schema } from './contractSchema'
import { validateCompanyPublicH2Semantics } from './contractSemantics'
import { parseStrictJson, type StrictJsonValue } from './strictJson'

export { CompanyPublicH2ContractError } from './contractErrors'
export type ParsedCompanyPublicH2 = Readonly<{ canonicalSource: StrictJsonValue; dto: CompanyPublicH2 }>

function freeze(value: StrictJsonValue): StrictJsonValue {
  if (Array.isArray(value)) value.forEach(freeze)
  else if (value !== null && typeof value === 'object') Object.values(value).forEach(freeze)
  return Object.freeze(value)
}

/**
 * Parses raw embedded state exactly once.  Schema and semantic checks happen
 * before digest verification, so a syntactically valid but unsafe DTO never
 * reaches React merely because an attacker supplied a digest for it.
 */
export async function parseCompanyPublicH2(raw: string, cryptoImpl?: Pick<Crypto, 'subtle'>): Promise<ParsedCompanyPublicH2> {
  let source: StrictJsonValue
  try {
    source = parseStrictJson(raw)
    const dto = object(source, 'root')
    validateCompanyPublicH2Schema(dto)
    validateCompanyPublicH2Semantics(dto)
    // The full DTO cap includes its digest; digest input deliberately omits it.
    canonicalFullProjectionBytes(source)
    canonicalJsonBytes(source)
    const expected = typeof dto.projection_digest === 'string' ? dto.projection_digest : ''
    if (!/^[0-9a-f]{64}$/.test(expected) || await canonicalProjectionDigest(source, cryptoImpl) !== expected) {
      throw new CompanyPublicH2ContractError('projection digest')
    }
    freeze(source)
    return Object.freeze({ canonicalSource: source, dto })
  } catch (error) {
    if (error instanceof CompanyPublicH2ContractError) throw error
    throw new CompanyPublicH2ContractError(error instanceof Error ? error.message : 'invalid public H2 projection')
  }
}
