import { toUserMessage } from '../auth/errors'
import { ApiHttpError } from '../lib/api'

export type CompanyAdminOperation =
  | 'summary'
  | 'usersStats'
  | 'invitesList'
  | 'inviteCreate'
  | 'limitUpdate'
  | 'detach'

export const COMPANY_ADMIN_TEXT = {
  sessionExpired: 'Сессия истекла или недостаточно прав. Войдите снова.',
  serverUnavailable: 'Сервер временно недоступен. Попробуйте позже.',
  loadingSummary: 'Загружаем обзор компании...',
  loadingUsers: 'Загружаем сотрудников...',
  loadingInvites: 'Загружаем приглашения...',
  emptyUsers: 'Сотрудники не найдены.',
  emptyInvites: 'Нет активных приглашений.',
  inviteCreated: 'Приглашение отправлено.',
  limitUpdated: 'Лимит сотрудника обновлён.',
  userDetached: 'Сотрудник удалён из компании.',
  retry: 'Повторить',
} as const

const OPERATION_FALLBACK: Record<CompanyAdminOperation, string> = {
  summary: 'Не удалось загрузить обзор компании.',
  usersStats: 'Не удалось загрузить список сотрудников.',
  invitesList: 'Не удалось загрузить приглашения.',
  inviteCreate: 'Не удалось отправить приглашение.',
  limitUpdate: 'Не удалось обновить лимит сотрудника.',
  detach: 'Не удалось удалить сотрудника из компании.',
}

const BAD_REQUEST_FALLBACK: Record<CompanyAdminOperation, string> = {
  summary: 'Некорректный запрос к обзору компании.',
  usersStats: 'Некорректный запрос списка сотрудников.',
  invitesList: 'Некорректный запрос списка приглашений.',
  inviteCreate: 'Проверьте поля формы приглашения.',
  limitUpdate: 'Проверьте параметры изменения лимита.',
  detach: 'Некорректный запрос удаления сотрудника.',
}

export function formatCompanyAdminError(
  error: unknown,
  options: { operation: CompanyAdminOperation },
): string {
  const operation = options.operation

  if (error instanceof ApiHttpError) {
    if (error.status === 401 || error.status === 403) {
      return COMPANY_ADMIN_TEXT.sessionExpired
    }
    if (error.status === 402) {
      return mapPaymentRequiredDetail(error.payload)
    }
    if (error.status === 404) {
      return mapNotFoundDetail(operation)
    }
    if (error.status === 409) {
      return mapConflictDetail(error.payload, operation)
    }
    if (error.status === 400) {
      return mapBadRequestDetail(error.payload, operation)
    }
    if (error.status >= 500) {
      return COMPANY_ADMIN_TEXT.serverUnavailable
    }
  }

  return toUserMessage(error, OPERATION_FALLBACK[operation])
}

export function formatLimitUpdateSuccess(nextRemaining: number): string {
  return `Лимит обновлён. Текущий остаток сотрудника: ${nextRemaining}.`
}

export function formatDetachSuccess(email: string, releasedLimit: number): string {
  return `Сотрудник ${email} удалён. Освобождено лимита: ${releasedLimit}.`
}

function mapPaymentRequiredDetail(payload: unknown): string {
  const detail = extractApiDetail(payload).toLowerCase()
  if (detail.includes('insufficient_company_credits')) {
    return 'Недостаточно кредитов компании. Обратитесь к суперадминистратору для пополнения.'
  }
  if (detail.includes('insufficient_user_credits')) {
    return 'Недостаточно персонального лимита сотрудника.'
  }
  return 'Недостаточно кредитов для выполнения операции.'
}

function mapNotFoundDetail(operation: CompanyAdminOperation): string {
  if (operation === 'detach' || operation === 'limitUpdate') {
    return 'Сотрудник не найден.'
  }
  if (operation === 'summary') {
    return 'Компания не найдена.'
  }
  return OPERATION_FALLBACK[operation]
}

function mapConflictDetail(
  payload: unknown,
  operation: CompanyAdminOperation,
): string {
  const detail = extractApiDetail(payload).toLowerCase()
  if (operation === 'inviteCreate') {
    if (detail.includes('email already in a company')) {
      return 'Этот email уже привязан к другой компании.'
    }
    if (detail.includes('email already invited to another company')) {
      return 'Этот email уже приглашён в другую компанию.'
    }
    if (detail.includes('active invite already exists')) {
      return 'Для этого email уже есть активное приглашение.'
    }
  }
  if (operation === 'limitUpdate') {
    if (detail.includes('allocation exceeds company pool balance')) {
      return 'Нельзя установить лимит: сумма лимитов превышает общий баланс компании.'
    }
  }
  return toUserMessage(
    new ApiHttpError(409, payload),
    OPERATION_FALLBACK[operation],
  )
}

function mapBadRequestDetail(
  payload: unknown,
  operation: CompanyAdminOperation,
): string {
  const detail = extractApiDetail(payload).toLowerCase()
  if (operation === 'limitUpdate') {
    if (detail.includes('invalid delta')) {
      return 'Изменение лимита не может быть нулевым.'
    }
    if (detail.includes('limit cannot be negative')) {
      return 'Лимит не может быть отрицательным.'
    }
    if (detail.includes('reason is required')) {
      return 'Укажите причину изменения лимита.'
    }
  }
  if (operation === 'detach' && detail.includes('cannot detach self')) {
    return 'Нельзя удалить самого себя.'
  }
  return toUserMessage(new ApiHttpError(400, payload), BAD_REQUEST_FALLBACK[operation])
}

function extractApiDetail(payload: unknown): string {
  if (typeof payload === 'string' && payload.trim()) {
    return payload.trim()
  }
  if (!payload || typeof payload !== 'object') {
    return ''
  }
  const detail = (payload as Record<string, unknown>).detail
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim()
  }
  if (!detail || typeof detail !== 'object') {
    return ''
  }
  const detailRecord = detail as Record<string, unknown>
  const message = detailRecord.message
  if (typeof message === 'string' && message.trim()) {
    return message.trim()
  }
  const code = detailRecord.code
  if (typeof code === 'string' && code.trim()) {
    return code.trim()
  }
  return ''
}
