import type { PublicH2ArbitrationOutcomeDto, PublicH2ArbitrationRoleDto, PublicH2SafeCaseDetailDto } from './contractSchema'
import type { StrictJsonInteger } from './strictJson'

const ROLE_LABELS: Readonly<Record<PublicH2ArbitrationRoleDto, string>> = {
  plaintiff: 'Истец', respondent: 'Ответчик', other: 'Иная роль', unattributed: 'Роль не определена',
}
const OUTCOME_LABELS: Readonly<Record<PublicH2ArbitrationOutcomeDto, string>> = {
  won: 'Требования удовлетворены', lost: 'В удовлетворении отказано', returned: 'Возвращено', unknown: 'Результат не определён',
}

export function arbitrationRoleLabel(value: PublicH2ArbitrationRoleDto): string { return ROLE_LABELS[value] }
export function arbitrationOutcomeLabel(value: PublicH2ArbitrationOutcomeDto): string { return OUTCOME_LABELS[value] }
export function arbitrationCount(value: StrictJsonInteger | null): string { return value?.token ?? '—' }
export function arbitrationPercent(value: string | null): string { return value === null ? '—' : `${value} %` }
export function arbitrationYear(value: StrictJsonInteger | null): string { return value?.token ?? 'Год не указан' }
export function arbitrationCaseLabel(value: PublicH2SafeCaseDetailDto): string { return value.case_number ?? value.case_public_id }
export function arbitrationCollectionLabel(value: 'complete_collection' | 'returned_slice' | 'not_applicable'): string {
  return value === 'complete_collection' ? 'Полная коллекция' : value === 'returned_slice' ? 'Полученная часть коллекции' : 'Коллекция недоступна'
}
