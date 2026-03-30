import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  clearClaimSession,
  hasClaimSession,
  readClaimSession,
  writeClaimSession,
} from './claimSession'

describe('claimSession', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  afterEach(() => {
    sessionStorage.clear()
  })

  it('writes and reads claim session', () => {
    writeClaimSession({ claimId: 101, editToken: 'token-abc' })

    const value = readClaimSession()
    expect(value).not.toBeNull()
    expect(value?.claimId).toBe(101)
    expect(value?.editToken).toBe('token-abc')
    expect(typeof value?.savedAt).toBe('string')
    expect(hasClaimSession()).toBe(true)
  })

  it('clears session value', () => {
    writeClaimSession({ claimId: 101, editToken: 'token-abc' })
    clearClaimSession()

    expect(readClaimSession()).toBeNull()
    expect(hasClaimSession()).toBe(false)
  })

  it('drops invalid json from storage', () => {
    sessionStorage.setItem('claims.public.session.v1', '{broken-json')

    expect(readClaimSession()).toBeNull()
    expect(sessionStorage.getItem('claims.public.session.v1')).toBeNull()
  })

  it('drops invalid shape from storage', () => {
    sessionStorage.setItem(
      'claims.public.session.v1',
      JSON.stringify({ claimId: 0, editToken: '', savedAt: '' }),
    )

    expect(readClaimSession()).toBeNull()
    expect(sessionStorage.getItem('claims.public.session.v1')).toBeNull()
  })
})
