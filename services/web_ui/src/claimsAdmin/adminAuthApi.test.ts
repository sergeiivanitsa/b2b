import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  confirmClaimsAdminToken,
  logoutClaimsAdminSession,
  probeClaimsAdminSession,
  requestClaimsAdminLink,
} from './adminAuthApi'

describe('adminAuthApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('POST /admin/auth/request-link normalizes email', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ status: 'ok' }),
        {
          status: 200,
          headers: { 'content-type': 'application/json' },
        },
      ),
    )

    const payload = await requestClaimsAdminLink('  ADMIN@COMPANY.RU ')

    expect(payload.status).toBe('ok')
    const [path, options] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/admin/auth/request-link')
    expect(options?.method).toBe('POST')
    expect(options?.body).toBe(JSON.stringify({ email: 'admin@company.ru' }))
  })

  it('POST /admin/auth/confirm sends token payload', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ status: 'ok' }),
        {
          status: 200,
          headers: { 'content-type': 'application/json' },
        },
      ),
    )

    const payload = await confirmClaimsAdminToken('token-1')

    expect(payload.status).toBe('ok')
    const [path, options] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/admin/auth/confirm')
    expect(options?.body).toBe(JSON.stringify({ token: 'token-1' }))
  })

  it('probe uses /admin/claims endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ items: [] }),
        {
          status: 200,
          headers: { 'content-type': 'application/json' },
        },
      ),
    )

    await probeClaimsAdminSession()

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [path] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/admin/claims?limit=1&offset=0')
  })

  it('logout uses shared /auth/logout endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ status: 'ok' }),
        {
          status: 200,
          headers: { 'content-type': 'application/json' },
        },
      ),
    )

    await logoutClaimsAdminSession()

    const [path, options] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/auth/logout')
    expect(options?.method).toBe('POST')
  })
})

