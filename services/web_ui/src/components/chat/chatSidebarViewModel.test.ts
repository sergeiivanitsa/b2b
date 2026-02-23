import { describe, expect, it } from 'vitest'

import type { ChatMessage, ChatThread } from '../../types/chat'
import {
  CHAT_SIDEBAR_FALLBACK_PREVIEW,
  CHAT_SIDEBAR_PREVIEW_MAX_CHARS,
  CHAT_SIDEBAR_UNKNOWN_DAY_LABEL,
  buildChatSidebarGroups,
  buildFirstAssistantPreview,
  formatChatTimestamp,
  formatDayHeader,
  getDayKey,
  parseTimestamp,
  sortThreadsByUpdatedAtDesc,
  timestampToEpochMs,
  truncatePreview,
} from './chatSidebarViewModel'

function createMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: overrides.id ?? 'message-id',
    role: overrides.role ?? 'user',
    content: overrides.content ?? 'Message',
    status: overrides.status ?? 'completed',
    clientMessageId: overrides.clientMessageId ?? null,
    createdAt: overrides.createdAt ?? '2026-02-20T10:00:00.000Z',
  }
}

function createThread(overrides: Partial<ChatThread> = {}): ChatThread {
  return {
    id: overrides.id ?? 'thread-id',
    title: overrides.title ?? 'Thread',
    conversationId: overrides.conversationId ?? null,
    messages: overrides.messages ?? [],
    createdAt: overrides.createdAt ?? '2026-02-20T10:00:00.000Z',
    updatedAt: overrides.updatedAt ?? '2026-02-20T10:00:00.000Z',
  }
}

describe('chatSidebarViewModel', () => {
  describe('timestamp helpers', () => {
    it('parses valid timestamps and returns null for invalid values', () => {
      expect(parseTimestamp('2026-02-20T10:00:00.000Z')).not.toBeNull()
      expect(parseTimestamp('not-a-date')).toBeNull()
    })

    it('returns fallback epoch for invalid timestamps', () => {
      expect(timestampToEpochMs('not-a-date', 123)).toBe(123)
    })
  })

  describe('sortThreadsByUpdatedAtDesc', () => {
    it('sorts by updatedAt descending and keeps invalid timestamps at the bottom', () => {
      const source = [
        createThread({ id: 't-1', updatedAt: '2026-02-20T10:00:00.000Z' }),
        createThread({ id: 't-2', updatedAt: 'invalid' }),
        createThread({ id: 't-3', updatedAt: '2026-02-21T08:00:00.000Z' }),
      ]

      const sorted = sortThreadsByUpdatedAtDesc(source)

      expect(sorted.map((thread) => thread.id)).toEqual(['t-3', 't-1', 't-2'])
      expect(source.map((thread) => thread.id)).toEqual(['t-1', 't-2', 't-3'])
    })
  })

  describe('preview helpers', () => {
    it('uses the earliest assistant message by createdAt, not the message array order', () => {
      const thread = createThread({
        messages: [
          createMessage({
            id: 'assistant-late',
            role: 'assistant',
            content: 'Поздний ответ',
            createdAt: '2026-02-20T10:05:00.000Z',
          }),
          createMessage({
            id: 'assistant-early',
            role: 'assistant',
            content: 'Ранний ответ',
            createdAt: '2026-02-20T10:01:00.000Z',
          }),
        ],
      })

      expect(buildFirstAssistantPreview(thread)).toBe('Ранний ответ')
    })

    it('uses fallback when there is no non-empty assistant message', () => {
      const noAssistantThread = createThread({
        messages: [
          createMessage({
            id: 'user-1',
            role: 'user',
            content: 'Hello',
          }),
        ],
      })
      const emptyAssistantThread = createThread({
        messages: [
          createMessage({
            id: 'assistant-empty',
            role: 'assistant',
            content: '   ',
          }),
        ],
      })

      expect(buildFirstAssistantPreview(noAssistantThread)).toBe(CHAT_SIDEBAR_FALLBACK_PREVIEW)
      expect(buildFirstAssistantPreview(emptyAssistantThread)).toBe(CHAT_SIDEBAR_FALLBACK_PREVIEW)
    })

    it('truncates long assistant preview and appends ellipsis', () => {
      const longPreview = 'a'.repeat(CHAT_SIDEBAR_PREVIEW_MAX_CHARS + 5)
      const thread = createThread({
        messages: [
          createMessage({
            id: 'assistant-long',
            role: 'assistant',
            content: longPreview,
          }),
        ],
      })

      expect(buildFirstAssistantPreview(thread)).toBe(
        `${'a'.repeat(CHAT_SIDEBAR_PREVIEW_MAX_CHARS)}...`,
      )
      expect(truncatePreview('  a   b  c  ', 7)).toBe('a b c')
    })
  })

  describe('date formatting', () => {
    it('formats createdAt as dd.MM.yy HH:mm in Europe/Berlin', () => {
      expect(formatChatTimestamp('2026-02-20T12:34:00.000Z')).toBe('20.02.26 13:34')
    })

    it('formats day headers in ru-RU with capitalized weekday', () => {
      expect(formatDayHeader('2026-02-20T12:34:00.000Z')).toBe('Пятница 20.02.26')
    })
  })

  describe('grouping', () => {
    it('builds Today group and date groups in descending day order', () => {
      const now = new Date('2026-02-20T23:30:00.000Z') // 2026-02-21 00:30 in Europe/Berlin
      const threads = [
        createThread({
          id: 't-today-older',
          updatedAt: '2026-02-20T23:10:00.000Z',
          createdAt: '2026-02-20T20:00:00.000Z',
          messages: [createMessage({ role: 'assistant', content: 'old today answer' })],
        }),
        createThread({
          id: 't-prev-day',
          updatedAt: '2026-02-20T22:10:00.000Z',
          createdAt: '2026-02-20T19:00:00.000Z',
          messages: [createMessage({ role: 'assistant', content: 'yesterday answer' })],
        }),
        createThread({
          id: 't-today-newer',
          updatedAt: '2026-02-20T23:20:00.000Z',
          createdAt: '2026-02-20T21:00:00.000Z',
          messages: [createMessage({ role: 'assistant', content: 'new today answer' })],
        }),
      ]

      const groups = buildChatSidebarGroups(threads, { now })

      expect(groups).toHaveLength(2)
      expect(groups[0]?.label).toBe('Сегодня')
      expect(groups[0]?.items.map((item) => item.threadId)).toEqual([
        't-today-newer',
        't-today-older',
      ])
      expect(groups[1]?.label).toBe('Пятница 20.02.26')
      expect(groups[1]?.items.map((item) => item.threadId)).toEqual(['t-prev-day'])
    })

    it('is stable around UTC midnight by using Europe/Berlin day keys', () => {
      const now = new Date('2026-02-20T23:30:00.000Z') // Berlin already next day
      const sameBerlinDay = '2026-02-20T23:15:00.000Z'
      const previousBerlinDay = '2026-02-20T22:15:00.000Z'

      expect(getDayKey(now)).toBe(getDayKey(sameBerlinDay))
      expect(getDayKey(now)).not.toBe(getDayKey(previousBerlinDay))
    })

    it('sends invalid updatedAt to the unknown day group', () => {
      const groups = buildChatSidebarGroups(
        [
          createThread({
            id: 't-valid',
            updatedAt: '2026-02-21T08:00:00.000Z',
          }),
          createThread({
            id: 't-invalid',
            updatedAt: 'invalid',
          }),
        ],
        {
          now: new Date('2026-02-21T09:00:00.000Z'),
        },
      )

      expect(groups).toHaveLength(2)
      expect(groups[1]?.label).toBe(CHAT_SIDEBAR_UNKNOWN_DAY_LABEL)
      expect(groups[1]?.items.map((item) => item.threadId)).toEqual(['t-invalid'])
    })
  })
})
