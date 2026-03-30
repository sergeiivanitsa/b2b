const CLAIM_SESSION_STORAGE_KEY = 'claims.public.session.v1'

export type ClaimSession = {
  claimId: number
  editToken: string
  savedAt: string
}

export type ClaimSessionInput = {
  claimId: number
  editToken: string
}

export function readClaimSession(): ClaimSession | null {
  const storage = getSessionStorage()
  if (!storage) {
    return null
  }

  const raw = storage.getItem(CLAIM_SESSION_STORAGE_KEY)
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw)
    if (!isClaimSession(parsed)) {
      storage.removeItem(CLAIM_SESSION_STORAGE_KEY)
      return null
    }
    return parsed
  } catch {
    storage.removeItem(CLAIM_SESSION_STORAGE_KEY)
    return null
  }
}

export function writeClaimSession(input: ClaimSessionInput): void {
  const storage = getSessionStorage()
  if (!storage) {
    return
  }

  const claimId = normalizeClaimId(input.claimId)
  const editToken = normalizeEditToken(input.editToken)
  const nextValue: ClaimSession = {
    claimId,
    editToken,
    savedAt: new Date().toISOString(),
  }
  storage.setItem(CLAIM_SESSION_STORAGE_KEY, JSON.stringify(nextValue))
}

export function clearClaimSession(): void {
  const storage = getSessionStorage()
  if (!storage) {
    return
  }
  storage.removeItem(CLAIM_SESSION_STORAGE_KEY)
}

export function hasClaimSession(): boolean {
  return readClaimSession() !== null
}

function normalizeClaimId(value: number): number {
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error('claimId must be a positive integer')
  }
  return value
}

function normalizeEditToken(value: string): string {
  const normalized = value.trim()
  if (!normalized) {
    throw new Error('editToken is required')
  }
  return normalized
}

function isClaimSession(value: unknown): value is ClaimSession {
  if (!value || typeof value !== 'object') {
    return false
  }
  const record = value as Record<string, unknown>
  return (
    Number.isInteger(record.claimId) &&
    (record.claimId as number) > 0 &&
    typeof record.editToken === 'string' &&
    record.editToken.trim().length > 0 &&
    typeof record.savedAt === 'string' &&
    record.savedAt.length > 0
  )
}

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null
  }
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}
