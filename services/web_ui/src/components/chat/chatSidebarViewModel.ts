import type { ChatMessage, ChatThread } from '../../types/chat'

export const CHAT_SIDEBAR_PREVIEW_MAX_CHARS = 72
export const CHAT_SIDEBAR_TIME_ZONE = 'Europe/Berlin'
export const CHAT_SIDEBAR_LOCALE = 'ru-RU'
export const CHAT_SIDEBAR_FALLBACK_PREVIEW = 'Новый чат'
export const CHAT_SIDEBAR_TODAY_LABEL = 'Сегодня'
export const CHAT_SIDEBAR_UNKNOWN_DAY_LABEL = 'Без даты'
export const CHAT_SIDEBAR_INVALID_DATE_LABEL = '—'
export const CHAT_SIDEBAR_UNKNOWN_DAY_KEY = '__unknown_day__'

type DateFormatParts = {
  day: string
  month: string
  year: string
  hour?: string
  minute?: string
  weekday?: string
}

type ResolvedOptions = {
  now: Date
  locale: string
  timeZone: string
  previewMaxChars: number
  fallbackPreview: string
  todayLabel: string
  unknownDayLabel: string
  invalidDateLabel: string
}

export type ChatSidebarViewModelOptions = {
  now?: Date
  locale?: string
  timeZone?: string
  previewMaxChars?: number
  fallbackPreview?: string
  todayLabel?: string
  unknownDayLabel?: string
  invalidDateLabel?: string
}

export type ChatSidebarThreadViewModel = {
  threadId: string
  thread: ChatThread
  preview: string
  createdAtLabel: string
  updatedAtMs: number
  dayKey: string
}

export type ChatSidebarGroupViewModel = {
  key: string
  label: string
  items: ChatSidebarThreadViewModel[]
}

export function parseTimestamp(value: string): Date | null {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return null
  }
  return parsed
}

export function timestampToEpochMs(
  value: string,
  fallback: number = Number.NEGATIVE_INFINITY,
): number {
  const parsed = parseTimestamp(value)
  return parsed ? parsed.getTime() : fallback
}

export function sortThreadsByUpdatedAtDesc(threads: ChatThread[]): ChatThread[] {
  return [...threads].sort((left, right) => {
    const leftUpdatedAtMs = timestampToEpochMs(left.updatedAt)
    const rightUpdatedAtMs = timestampToEpochMs(right.updatedAt)

    if (leftUpdatedAtMs !== rightUpdatedAtMs) {
      return rightUpdatedAtMs > leftUpdatedAtMs ? 1 : -1
    }

    return left.id.localeCompare(right.id)
  })
}

export function truncatePreview(input: string, maxChars: number = CHAT_SIDEBAR_PREVIEW_MAX_CHARS): string {
  const normalized = normalizeText(input)
  if (maxChars <= 0) {
    return ''
  }
  if (normalized.length <= maxChars) {
    return normalized
  }
  return `${normalized.slice(0, maxChars).trimEnd()}...`
}

export function getFirstAssistantMessage(messages: ChatMessage[]): ChatMessage | null {
  const candidates = messages
    .map((message, index) => ({
      message,
      index,
      createdAtMs: timestampToEpochMs(message.createdAt, Number.POSITIVE_INFINITY),
      hasPreviewContent:
        message.role === 'assistant' && normalizeText(message.content).length > 0,
    }))
    .filter((candidate) => candidate.hasPreviewContent)

  if (candidates.length === 0) {
    return null
  }

  candidates.sort((left, right) => {
    if (left.createdAtMs !== right.createdAtMs) {
      return left.createdAtMs < right.createdAtMs ? -1 : 1
    }
    return left.index - right.index
  })

  return candidates[0].message
}

export function buildFirstAssistantPreview(
  thread: ChatThread,
  options: Pick<ChatSidebarViewModelOptions, 'previewMaxChars' | 'fallbackPreview'> = {},
): string {
  const previewMaxChars =
    options.previewMaxChars && options.previewMaxChars > 0
      ? options.previewMaxChars
      : CHAT_SIDEBAR_PREVIEW_MAX_CHARS
  const fallbackPreview = options.fallbackPreview ?? CHAT_SIDEBAR_FALLBACK_PREVIEW

  const assistantMessage = getFirstAssistantMessage(thread.messages)
  if (!assistantMessage) {
    return fallbackPreview
  }

  const preview = truncatePreview(assistantMessage.content, previewMaxChars)
  return preview || fallbackPreview
}

export function getDayKey(
  value: string | Date,
  options: Pick<ChatSidebarViewModelOptions, 'locale' | 'timeZone'> = {},
): string | null {
  const locale = options.locale ?? CHAT_SIDEBAR_LOCALE
  const timeZone = options.timeZone ?? CHAT_SIDEBAR_TIME_ZONE
  const date = typeof value === 'string' ? parseTimestamp(value) : value

  if (!date || Number.isNaN(date.getTime())) {
    return null
  }

  const parts = getDateFormatParts(date, locale, timeZone, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
  if (!parts) {
    return null
  }

  return `${parts.year}-${parts.month}-${parts.day}`
}

export function formatChatTimestamp(
  value: string,
  options: Pick<ChatSidebarViewModelOptions, 'locale' | 'timeZone' | 'invalidDateLabel'> = {},
): string {
  const locale = options.locale ?? CHAT_SIDEBAR_LOCALE
  const timeZone = options.timeZone ?? CHAT_SIDEBAR_TIME_ZONE
  const invalidDateLabel = options.invalidDateLabel ?? CHAT_SIDEBAR_INVALID_DATE_LABEL

  const parsed = parseTimestamp(value)
  if (!parsed) {
    return invalidDateLabel
  }

  const parts = getDateFormatParts(parsed, locale, timeZone, {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    hourCycle: 'h23',
  })
  if (!parts || !parts.hour || !parts.minute) {
    return invalidDateLabel
  }

  return `${parts.day}.${parts.month}.${parts.year} ${parts.hour}:${parts.minute}`
}

export function formatDayHeader(
  value: string | Date,
  options: Pick<ChatSidebarViewModelOptions, 'locale' | 'timeZone' | 'unknownDayLabel'> = {},
): string {
  const locale = options.locale ?? CHAT_SIDEBAR_LOCALE
  const timeZone = options.timeZone ?? CHAT_SIDEBAR_TIME_ZONE
  const unknownDayLabel = options.unknownDayLabel ?? CHAT_SIDEBAR_UNKNOWN_DAY_LABEL
  const date = typeof value === 'string' ? parseTimestamp(value) : value

  if (!date || Number.isNaN(date.getTime())) {
    return unknownDayLabel
  }

  const parts = getDateFormatParts(date, locale, timeZone, {
    weekday: 'long',
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
  })
  if (!parts || !parts.weekday) {
    return unknownDayLabel
  }

  return `${capitalizeFirst(parts.weekday, locale)} ${parts.day}.${parts.month}.${parts.year}`
}

export function buildChatSidebarGroups(
  threads: ChatThread[],
  options: ChatSidebarViewModelOptions = {},
): ChatSidebarGroupViewModel[] {
  const resolved = resolveOptions(options)
  const sortedThreads = sortThreadsByUpdatedAtDesc(threads)
  const todayKey =
    getDayKey(resolved.now, { locale: resolved.locale, timeZone: resolved.timeZone }) ??
    CHAT_SIDEBAR_UNKNOWN_DAY_KEY

  const groups = new Map<string, ChatSidebarGroupViewModel>()

  for (const thread of sortedThreads) {
    const updatedDate = parseTimestamp(thread.updatedAt)
    const dayKey =
      (updatedDate &&
        getDayKey(updatedDate, {
          locale: resolved.locale,
          timeZone: resolved.timeZone,
        })) ??
      CHAT_SIDEBAR_UNKNOWN_DAY_KEY

    const label =
      dayKey === todayKey
        ? resolved.todayLabel
        : updatedDate
          ? formatDayHeader(updatedDate, {
              locale: resolved.locale,
              timeZone: resolved.timeZone,
              unknownDayLabel: resolved.unknownDayLabel,
            })
          : resolved.unknownDayLabel

    const existingGroup = groups.get(dayKey)
    const item: ChatSidebarThreadViewModel = {
      threadId: thread.id,
      thread,
      preview: buildFirstAssistantPreview(thread, {
        previewMaxChars: resolved.previewMaxChars,
        fallbackPreview: resolved.fallbackPreview,
      }),
      createdAtLabel: formatChatTimestamp(thread.createdAt, {
        locale: resolved.locale,
        timeZone: resolved.timeZone,
        invalidDateLabel: resolved.invalidDateLabel,
      }),
      updatedAtMs: timestampToEpochMs(thread.updatedAt),
      dayKey,
    }

    if (existingGroup) {
      existingGroup.items.push(item)
      continue
    }

    groups.set(dayKey, {
      key: dayKey,
      label,
      items: [item],
    })
  }

  return [...groups.values()]
}

function resolveOptions(options: ChatSidebarViewModelOptions): ResolvedOptions {
  const now =
    options.now && !Number.isNaN(options.now.getTime()) ? options.now : new Date()
  return {
    now,
    locale: options.locale ?? CHAT_SIDEBAR_LOCALE,
    timeZone: options.timeZone ?? CHAT_SIDEBAR_TIME_ZONE,
    previewMaxChars:
      options.previewMaxChars && options.previewMaxChars > 0
        ? options.previewMaxChars
        : CHAT_SIDEBAR_PREVIEW_MAX_CHARS,
    fallbackPreview: options.fallbackPreview ?? CHAT_SIDEBAR_FALLBACK_PREVIEW,
    todayLabel: options.todayLabel ?? CHAT_SIDEBAR_TODAY_LABEL,
    unknownDayLabel: options.unknownDayLabel ?? CHAT_SIDEBAR_UNKNOWN_DAY_LABEL,
    invalidDateLabel: options.invalidDateLabel ?? CHAT_SIDEBAR_INVALID_DATE_LABEL,
  }
}

function getDateFormatParts(
  date: Date,
  locale: string,
  timeZone: string,
  options: Intl.DateTimeFormatOptions,
): DateFormatParts | null {
  const formatter = new Intl.DateTimeFormat(locale, {
    ...options,
    timeZone,
  })
  const parts = formatter.formatToParts(date)

  let day = ''
  let month = ''
  let year = ''
  let hour = ''
  let minute = ''
  let weekday = ''

  for (const part of parts) {
    if (part.type === 'day') {
      day = part.value
    } else if (part.type === 'month') {
      month = part.value
    } else if (part.type === 'year') {
      year = part.value
    } else if (part.type === 'hour') {
      hour = part.value
    } else if (part.type === 'minute') {
      minute = part.value
    } else if (part.type === 'weekday') {
      weekday = part.value
    }
  }

  if (!day || !month || !year) {
    return null
  }

  return {
    day,
    month,
    year,
    hour: hour || undefined,
    minute: minute || undefined,
    weekday: weekday || undefined,
  }
}

function normalizeText(value: string): string {
  return value.replace(/\s+/g, ' ').trim()
}

function capitalizeFirst(value: string, locale: string): string {
  if (!value) {
    return value
  }
  return value.charAt(0).toLocaleUpperCase(locale) + value.slice(1)
}
