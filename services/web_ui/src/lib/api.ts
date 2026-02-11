const DEFAULT_API_BASE_PATH = '/api'

const API_BASE_PATH = normalizeApiBasePath(
  import.meta.env.VITE_API_BASE_PATH || DEFAULT_API_BASE_PATH,
)

export type ApiFetchOptions = Omit<RequestInit, 'body'> & {
  body?: BodyInit | Record<string, unknown> | unknown[] | null
}

export class ApiHttpError extends Error {
  readonly status: number
  readonly payload: unknown

  constructor(status: number, payload: unknown) {
    super(`API request failed with status ${status}`)
    this.name = 'ApiHttpError'
    this.status = status
    this.payload = payload
  }
}

export async function apiFetchRaw(
  path: string,
  options: ApiFetchOptions = {},
): Promise<Response> {
  const { body, headers, credentials, ...rest } = options
  const requestHeaders = new Headers(headers ?? undefined)
  const requestBody = prepareRequestBody(body, requestHeaders)

  return fetch(buildApiUrl(path), {
    ...rest,
    headers: requestHeaders,
    body: requestBody,
    credentials: credentials ?? 'include',
  })
}

export async function apiFetchJson<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const response = await apiFetchRaw(path, options)
  const payload = await parseResponsePayload(response)

  if (!response.ok) {
    throw new ApiHttpError(response.status, payload)
  }

  return payload as T
}

function normalizeApiBasePath(value: string): string {
  const withLeadingSlash = value.startsWith('/') ? value : `/${value}`
  const withoutTrailingSlash = withLeadingSlash.replace(/\/+$/, '')
  return withoutTrailingSlash || DEFAULT_API_BASE_PATH
}

function buildApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path
  }
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  if (
    normalizedPath === API_BASE_PATH ||
    normalizedPath.startsWith(`${API_BASE_PATH}/`)
  ) {
    return normalizedPath
  }
  return `${API_BASE_PATH}${normalizedPath}`
}

function prepareRequestBody(
  body: ApiFetchOptions['body'],
  headers: Headers,
): BodyInit | null | undefined {
  if (body === undefined) {
    return undefined
  }
  if (body === null) {
    return null
  }
  if (isBodyInit(body)) {
    return body
  }
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  return JSON.stringify(body)
}

function isBodyInit(value: unknown): value is BodyInit {
  if (
    typeof value === 'string' ||
    value instanceof Blob ||
    value instanceof FormData ||
    value instanceof URLSearchParams ||
    value instanceof ArrayBuffer ||
    ArrayBuffer.isView(value)
  ) {
    return true
  }
  if (typeof ReadableStream !== 'undefined' && value instanceof ReadableStream) {
    return true
  }
  return false
}

async function parseResponsePayload(response: Response): Promise<unknown> {
  if (response.status === 204 || response.status === 205) {
    return null
  }

  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json') || contentType.includes('+json')) {
    return response.json()
  }

  const text = await response.text()
  return text || null
}
