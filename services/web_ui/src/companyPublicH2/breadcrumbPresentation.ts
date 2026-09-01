type LegalForm = Readonly<{
  short: string
  aliases: readonly string[]
}>

const LEGAL_FORMS: readonly LegalForm[] = [
  {
    short: 'ООО',
    aliases: [
      'Общество с ограниченной ответственностью',
      'Общества с ограниченной ответственностью',
      'ООО',
    ],
  },
  { short: 'АО', aliases: ['Акционерное общество', 'АО'] },
  { short: 'ОАО', aliases: ['Открытое акционерное общество', 'ОАО'] },
  { short: 'ЗАО', aliases: ['Закрытое акционерное общество', 'ЗАО'] },
  { short: 'ПАО', aliases: ['Публичное акционерное общество', 'ПАО'] },
  { short: 'ИП', aliases: ['Индивидуальный предприниматель', 'ИП'] },
]
const LEGAL_FORM_BOUNDARIES = new Set([' ', '"', '«'])

type LeadingForm = Readonly<{
  short: string
  remainder: string
}>

function normalizeCandidate(value: string | null | undefined): string {
  const normalized: string[] = []
  let pendingSpace = false
  for (const scalar of (value ?? '').normalize('NFC')) {
    const code = scalar.codePointAt(0)!
    const whitespace = (code >= 0x09 && code <= 0x0d)
      || (code >= 0x1c && code <= 0x20)
      || code === 0x85
      || code === 0xa0
      || code === 0x1680
      || (code >= 0x2000 && code <= 0x200a)
      || code === 0x2028
      || code === 0x2029
      || code === 0x202f
      || code === 0x205f
      || code === 0x3000
    if (whitespace) {
      pendingSpace = normalized.length > 0
      continue
    }
    if (pendingSpace) normalized.push(' ')
    normalized.push(scalar)
    pendingSpace = false
  }
  return normalized.join('')
}

function hasAliasBoundary(value: string, aliasLength: number): boolean {
  const remainder = value.slice(aliasLength)
  return remainder === '' || LEGAL_FORM_BOUNDARIES.has(remainder[0])
}

function foldLegalForm(value: string): string {
  const folded: string[] = []
  for (const scalar of value) {
    const code = scalar.codePointAt(0)!
    if ((code >= 0x41 && code <= 0x5a) || (code >= 0x410 && code <= 0x42f)) {
      folded.push(String.fromCodePoint(code + 0x20))
    } else if (code === 0x401) {
      folded.push('ё')
    } else {
      folded.push(scalar)
    }
  }
  return folded.join('')
}

function leadingKnownForm(value: string): LeadingForm | null {
  const folded = foldLegalForm(value)
  for (const form of LEGAL_FORMS) {
    for (const alias of form.aliases) {
      if (
        folded.startsWith(foldLegalForm(alias))
        && hasAliasBoundary(value, alias.length)
      ) {
        const remainder = value.slice(alias.length)
        return {
          short: form.short,
          remainder: remainder.startsWith(' ') ? remainder.slice(1) : remainder,
        }
      }
    }
  }
  return null
}

function compactLeadingKnownForm(value: string): Readonly<{ value: string; form: LeadingForm | null }> {
  const form = leadingKnownForm(value)
  if (form === null) return { value, form }
  return {
    value: form.remainder === '' ? form.short : `${form.short} ${form.remainder}`,
    form,
  }
}

function withInferredForm(form: LeadingForm, value: string): string {
  return value === '' ? form.short : `${form.short} ${value}`
}

export function formatCompactCompanyBreadcrumbLabel({
  signedLabel,
  shortName,
  legalFullName,
}: Readonly<{
  signedLabel: string
  shortName: string | null
  legalFullName: string
}>): string {
  const label = normalizeCandidate(signedLabel)
  const providerShortName = normalizeCandidate(shortName)
  const legalName = normalizeCandidate(legalFullName)

  if (providerShortName !== '') {
    const compactedShortName = compactLeadingKnownForm(providerShortName)
    if (compactedShortName.form !== null) return compactedShortName.value

    const inferredForm = leadingKnownForm(label) ?? leadingKnownForm(legalName)
    return inferredForm === null
      ? providerShortName
      : withInferredForm(inferredForm, providerShortName)
  }

  const compactedLabel = compactLeadingKnownForm(label)
  if (compactedLabel.form !== null) return compactedLabel.value

  const inferredForm = leadingKnownForm(legalName)
  return inferredForm === null ? label : withInferredForm(inferredForm, label)
}
