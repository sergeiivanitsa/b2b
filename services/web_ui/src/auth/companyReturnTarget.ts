const COMPANY_RETURN_TARGET_KEY = 'auth.company-return-target.v1'
const COMPANY_PATH_RE = /^\/company\/(?:(?:[0-9]{10}|[0-9]{12})(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?|(?:ooo|ao|oao|zao|pao|ip)-[a-z0-9]+(?:-[a-z0-9]+)*-(?:[0-9]{10}|[0-9]{12}))$/

export function storeCompanyReturnTarget(pathname: string): void {
  if (!COMPANY_PATH_RE.test(pathname)) return
  getSessionStorage()?.setItem(COMPANY_RETURN_TARGET_KEY, pathname)
}

export function consumeCompanyReturnTarget(): string | null {
  const storage = getSessionStorage()
  const value = storage?.getItem(COMPANY_RETURN_TARGET_KEY) ?? ''
  storage?.removeItem(COMPANY_RETURN_TARGET_KEY)
  return COMPANY_PATH_RE.test(value) ? value : null
}

function getSessionStorage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage
  } catch {
    return null
  }
}
