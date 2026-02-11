import { ApiHttpError, apiFetchRaw } from './api'

export type ChatStreamPayload = {
  conversation_id?: string
  client_message_id: string
  content: string
  stream: true
}

export type ChatStreamFinalData = {
  text: string
  usage?: unknown
  conversation_id?: string | null
}

export type ChatStreamErrorData = {
  code?: string
  message?: string
  retryable?: boolean
}

type ChatStreamCallbacks = {
  signal?: AbortSignal
  onDelta: (text: string) => void
  onFinal: (data: ChatStreamFinalData) => void
  onError: (data: ChatStreamErrorData) => void
}

type ParsedSseEvent = {
  event: string
  data: string
}

export async function streamChat(
  payload: ChatStreamPayload,
  callbacks: ChatStreamCallbacks,
): Promise<void> {
  const response = await apiFetchRaw('/v1/chat', {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    },
    body: payload,
    signal: callbacks.signal,
  })

  if (!response.ok) {
    const payloadError = await parseErrorPayload(response)
    throw new ApiHttpError(response.status, payloadError)
  }

  const body = response.body
  if (!body) {
    throw new Error('Streaming response body is not available.')
  }

  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let shouldStop = false

  try {
    while (!shouldStop) {
      const { value, done } = await reader.read()
      if (done) {
        buffer += decoder.decode()
        const processed = extractAndProcessBufferedEvents(buffer, callbacks)
        shouldStop = processed.shouldStop || processBufferedEvents(processed.buffer, callbacks)
        buffer = ''
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const processed = extractAndProcessBufferedEvents(buffer, callbacks)
      buffer = processed.buffer
      shouldStop = processed.shouldStop
    }
  } finally {
    reader.releaseLock()
  }
}

function extractAndProcessBufferedEvents(
  input: string,
  callbacks: ChatStreamCallbacks,
): { buffer: string; shouldStop: boolean } {
  let buffer = input
  let shouldStop = false

  while (!shouldStop) {
    const boundary = findEventBoundary(buffer)
    if (!boundary) {
      break
    }
    const rawEvent = buffer.slice(0, boundary.index)
    buffer = buffer.slice(boundary.index + boundary.length)
    const parsed = parseSseEvent(rawEvent)
    if (!parsed) {
      continue
    }
    shouldStop = dispatchEvent(parsed, callbacks)
  }

  return { buffer, shouldStop }
}

function processBufferedEvents(input: string, callbacks: ChatStreamCallbacks): boolean {
  const trimmed = input.trim()
  if (!trimmed) {
    return false
  }
  const parsed = parseSseEvent(input)
  if (!parsed) {
    return false
  }
  return dispatchEvent(parsed, callbacks)
}

function dispatchEvent(event: ParsedSseEvent, callbacks: ChatStreamCallbacks): boolean {
  const parsedData = parseEventData(event.data)
  if (event.event === 'delta') {
    if (typeof parsedData.text === 'string') {
      callbacks.onDelta(parsedData.text)
    }
    return false
  }
  if (event.event === 'final') {
    callbacks.onFinal({
      text: typeof parsedData.text === 'string' ? parsedData.text : '',
      usage: parsedData.usage,
      conversation_id: normalizeConversationId(parsedData.conversation_id),
    })
    return true
  }
  if (event.event === 'error') {
    callbacks.onError({
      code: typeof parsedData.code === 'string' ? parsedData.code : undefined,
      message: typeof parsedData.message === 'string' ? parsedData.message : undefined,
      retryable:
        typeof parsedData.retryable === 'boolean' ? parsedData.retryable : undefined,
    })
    return true
  }
  return false
}

function parseEventData(data: string): Record<string, unknown> {
  if (!data.trim()) {
    return {}
  }
  try {
    const parsed = JSON.parse(data) as unknown
    if (parsed && typeof parsed === 'object') {
      return parsed as Record<string, unknown>
    }
    return {}
  } catch {
    return {}
  }
}

function normalizeConversationId(value: unknown): string | null | undefined {
  if (value === null) {
    return null
  }
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value)
  }
  return undefined
}

function parseSseEvent(rawEvent: string): ParsedSseEvent | null {
  const lines = rawEvent.split(/\r\n|\n|\r/)
  let eventName = 'message'
  const dataLines: string[] = []

  for (const line of lines) {
    if (!line) {
      continue
    }
    if (line.startsWith(':')) {
      continue
    }
    const separatorIndex = line.indexOf(':')
    const field = separatorIndex >= 0 ? line.slice(0, separatorIndex) : line
    let value = separatorIndex >= 0 ? line.slice(separatorIndex + 1) : ''
    if (value.startsWith(' ')) {
      value = value.slice(1)
    }

    if (field === 'event') {
      eventName = value || eventName
      continue
    }
    if (field === 'data') {
      dataLines.push(value)
    }
  }

  if (dataLines.length === 0) {
    return null
  }

  return {
    event: eventName,
    data: dataLines.join('\n'),
  }
}

function findEventBoundary(input: string): { index: number; length: number } | null {
  const candidates = [
    findBoundaryCandidate(input.indexOf('\r\n\r\n'), 4),
    findBoundaryCandidate(input.indexOf('\n\n'), 2),
    findBoundaryCandidate(input.indexOf('\r\r'), 2),
  ].filter((candidate): candidate is { index: number; length: number } => candidate !== null)

  if (candidates.length === 0) {
    return null
  }

  candidates.sort((left, right) => left.index - right.index)
  return candidates[0]
}

function findBoundaryCandidate(
  index: number,
  length: number,
): { index: number; length: number } | null {
  if (index < 0) {
    return null
  }
  return { index, length }
}

async function parseErrorPayload(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json') || contentType.includes('+json')) {
    try {
      return await response.json()
    } catch {
      return { detail: 'Failed to parse error response.' }
    }
  }
  try {
    const text = await response.text()
    return text || null
  } catch {
    return null
  }
}
