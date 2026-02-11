import { ApiHttpError } from '../lib/api'

export function isUnauthorizedError(error: unknown): boolean {
  return error instanceof ApiHttpError && error.status === 401
}

export function toUserMessage(error: unknown, fallbackMessage: string): string {
  if (error instanceof ApiHttpError) {
    const detailMessage = extractDetailMessage(error.payload)
    if (detailMessage) {
      return detailMessage
    }
    if (error.status === 429) {
      return 'Too many requests. Please try again in a moment.'
    }
    if (error.status >= 500) {
      return 'Server is unavailable right now. Please try again later.'
    }
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallbackMessage
}

function extractDetailMessage(payload: unknown): string | null {
  if (typeof payload === 'string' && payload.trim()) {
    return payload.trim()
  }
  if (!payload || typeof payload !== 'object') {
    return null
  }
  const detail = (payload as Record<string, unknown>).detail
  return extractNestedDetail(detail)
}

function extractNestedDetail(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim()
  }
  if (!detail || typeof detail !== 'object') {
    return null
  }
  const detailRecord = detail as Record<string, unknown>
  const message = detailRecord.message
  if (typeof message === 'string' && message.trim()) {
    return message.trim()
  }
  const code = detailRecord.code
  if (typeof code === 'string' && code.trim()) {
    return code.replace(/_/g, ' ')
  }
  return null
}
