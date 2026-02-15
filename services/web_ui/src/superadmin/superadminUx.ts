import { toUserMessage } from '../auth/errors'
import { ApiHttpError } from '../lib/api'

export type SuperadminOperation = 'list' | 'status' | 'create' | 'view' | 'invite' | 'credits'

export const SUPERADMIN_TEXT = {
  sessionExpired: 'Session expired or insufficient permissions. Please sign in again.',
  organizationNotFound: 'Organization not found.',
  serverUnavailable: 'Server is unavailable right now. Please try again later.',
  loadingOrganizations: 'Loading organizations...',
  emptyOrganizations: 'No organizations found.',
  emptyFilteredOrganizations: 'No organizations match current filters.',
  emptyViewedOrganization: 'No organization loaded yet.',
  inviteSent: 'Invite sent.',
  creditsAdded: 'Credits added.',
  creditsAlreadyProcessed:
    'Request was already processed (idempotency). Balance may already be updated.',
  resetFilters: 'Reset filters',
  retry: 'Retry',
  newCreditRequest: 'New credit request',
} as const

const BAD_REQUEST_FALLBACK: Record<SuperadminOperation, string> = {
  list: 'Invalid request.',
  status: 'Invalid organization status update.',
  create: 'Invalid organization name.',
  view: 'Invalid organization ID.',
  invite: 'Invalid invite request.',
  credits: 'Invalid credits request.',
}

const OPERATION_FALLBACK: Record<SuperadminOperation, string> = {
  list: 'Could not load organizations. Please try again.',
  status: 'Could not update organization status. Please try again.',
  create: 'Could not create organization. Please try again.',
  view: 'Could not load organization. Please try again.',
  invite: 'Could not send invite. Please try again.',
  credits: 'Could not add credits. Please try again.',
}

function extractApiDetail(payload: unknown): string | null {
  if (typeof payload === 'string' && payload.trim()) {
    return payload.trim()
  }
  if (!payload || typeof payload !== 'object') {
    return null
  }
  const detail = (payload as Record<string, unknown>).detail
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim()
  }
  if (!detail || typeof detail !== 'object') {
    return null
  }
  const message = (detail as Record<string, unknown>).message
  if (typeof message === 'string' && message.trim()) {
    return message.trim()
  }
  return null
}

export function isCreditsDuplicateIdempotencyConflict(error: unknown): boolean {
  if (!(error instanceof ApiHttpError) || error.status !== 409) {
    return false
  }
  const detail = extractApiDetail(error.payload)?.toLowerCase() ?? ''
  return detail.includes('duplicate idempotency_key')
}

export function formatSuperadminError(
  error: unknown,
  options: { operation: SuperadminOperation; notFoundMessage?: string },
): string {
  const { operation, notFoundMessage = SUPERADMIN_TEXT.organizationNotFound } = options

  if (error instanceof ApiHttpError) {
    if (error.status === 401 || error.status === 403) {
      return SUPERADMIN_TEXT.sessionExpired
    }
    if (
      (operation === 'view' || operation === 'invite' || operation === 'credits') &&
      error.status === 404
    ) {
      return notFoundMessage
    }
    if (operation === 'invite' && error.status === 409) {
      return toUserMessage(error, 'Invite conflict.')
    }
    if (error.status === 400) {
      return toUserMessage(error, BAD_REQUEST_FALLBACK[operation])
    }
    if (error.status >= 500) {
      return SUPERADMIN_TEXT.serverUnavailable
    }
  }

  return toUserMessage(error, OPERATION_FALLBACK[operation])
}

export function formatCreditsSuccessMessage(ledgerId?: number): string {
  if (typeof ledgerId === 'number') {
    return `Credits added. Ledger ID: ${ledgerId}.`
  }
  return SUPERADMIN_TEXT.creditsAdded
}
