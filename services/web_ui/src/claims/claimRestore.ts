import { ApiHttpError } from '../lib/api'
import { getClaim, type PublicClaimSnapshot } from './claimsApi'
import { clearClaimSession, readClaimSession } from './claimSession'

export type RestoredClaim = {
  claimId: number
  editToken: string
  claim: PublicClaimSnapshot
}

export async function restoreClaimFromSession(): Promise<RestoredClaim> {
  const session = readClaimSession()
  if (!session) {
    throw new Error('missing_session')
  }

  try {
    const claim = await getClaim(session.claimId, session.editToken)
    return {
      claimId: session.claimId,
      editToken: session.editToken,
      claim,
    }
  } catch (error) {
    if (error instanceof ApiHttpError && (error.status === 401 || error.status === 404)) {
      clearClaimSession()
      throw new Error('invalid_session')
    }
    throw error
  }
}
