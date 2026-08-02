import { afterEach, describe, expect, it } from 'vitest'

import { consumeCompanyReturnTarget, storeCompanyReturnTarget } from './companyReturnTarget'

describe('company return target', () => {
  afterEach(() => sessionStorage.clear())

  it('stores only strict company paths and consumes them once', () => {
    storeCompanyReturnTarget('/company/7700000000-ooo-vektor')
    expect(consumeCompanyReturnTarget()).toBe('/company/7700000000-ooo-vektor')
    expect(consumeCompanyReturnTarget()).toBeNull()
  })

  it('does not store external or malformed targets', () => {
    storeCompanyReturnTarget('https://example.test/company/7700000000')
    storeCompanyReturnTarget('/company/7700000000-ООО')
    expect(consumeCompanyReturnTarget()).toBeNull()
  })
})
