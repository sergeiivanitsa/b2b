
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CHAT_UI_TEXT } from '../../constants/chatUiText'
import { cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChatMessage, ChatThread } from '../../types/chat'
import {
  CHAT_SIDEBAR_FALLBACK_PREVIEW,
  CHAT_SIDEBAR_TODAY_LABEL,
} from './chatSidebarViewModel'
import { ChatSidebar } from './ChatSidebar'

type RenderOptions = {
  activeThreadId?: string | null
}

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

function renderSidebar(threads: ChatThread[], options: RenderOptions = {}) {
  const onCreateThread = vi.fn<() => void>()
  const onSelectThread = vi.fn<(threadId: string) => void>()

  const result = render(
    <ChatSidebar
      threads={threads}
      activeThreadId={options.activeThreadId ?? null}
      onCreateThread={onCreateThread}
      onSelectThread={onSelectThread}
    />,
  )

  return {
    ...result,
    onCreateThread,
    onSelectThread,
  }
}

describe('ChatSidebar', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-02-21T08:30:00.000Z'))
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CHAT_UI_TEXT } from '../../constants/chatUiText'
  it('renders Today and dated groups with threads sorted by updatedAt desc', () => {
    const threads = [
      createThread({
        id: 'today-older',
        updatedAt: '2026-02-21T06:30:00.000Z',
        createdAt: '2026-02-21T04:00:00.000Z',
        messages: [createMessage({ role: 'assistant', content: 'Today older answer' })],
      }),
      createThread({
        id: 'previous-day',
        updatedAt: '2026-02-20T22:10:00.000Z',
        createdAt: '2026-02-20T19:00:00.000Z',
        messages: [createMessage({ role: 'assistant', content: 'Previous day answer' })],
      }),
      createThread({
        id: 'today-newer',
        updatedAt: '2026-02-21T07:30:00.000Z',
        createdAt: '2026-02-21T04:30:00.000Z',
        messages: [createMessage({ role: 'assistant', content: 'Today newer answer' })],
      }),
    ]

    const { container } = renderSidebar(threads)
    const groupTitles = [...container.querySelectorAll('.chat-sidebar__group-title')].map(
      (node) => node.textContent?.trim() ?? '',
    )

    expect(groupTitles[0]).toBe(CHAT_SIDEBAR_TODAY_LABEL)
    expect(groupTitles[1]).toContain('20.02.26')

    const titleRows = [...container.querySelectorAll('.chat-thread-item__title')].map(
      (node) => node.textContent?.trim() ?? '',
    )

    expect(titleRows).toEqual(['Today newer answer', 'Today older answer', 'Previous day answer'])
  })

  it('uses first assistant message by createdAt for preview, not message array position', () => {
    const thread = createThread({
      id: 'thread-preview',
      updatedAt: '2026-02-21T07:30:00.000Z',
      messages: [
        createMessage({
          id: 'assistant-late',
          role: 'assistant',
          content: 'Late assistant response',
          createdAt: '2026-02-21T07:05:00.000Z',
        }),
        createMessage({
          id: 'assistant-early',
          role: 'assistant',
          content: 'Early assistant response',
          createdAt: '2026-02-21T07:00:00.000Z',
        }),
      ],
    })

    const { container } = renderSidebar([thread])
    const titleRow = container.querySelector('.chat-thread-item__title')

    expect(titleRow?.textContent?.trim()).toBe('Early assistant response')
  })

  it('uses fallback preview for empty or user-only threads', () => {
    const emptyThread = createThread({
      id: 'thread-empty',
      updatedAt: '2026-02-21T07:10:00.000Z',
      messages: [],
    })
    const userOnlyThread = createThread({
      id: 'thread-user-only',
      updatedAt: '2026-02-21T07:00:00.000Z',
      messages: [createMessage({ id: 'user-1', role: 'user', content: 'Only user text' })],
    })

    const { container } = renderSidebar([emptyThread, userOnlyThread])
    const titleRows = [...container.querySelectorAll('.chat-thread-item__title')].map(
      (node) => node.textContent?.trim() ?? '',
    )

    expect(titleRows).toEqual([CHAT_SIDEBAR_FALLBACK_PREVIEW, CHAT_SIDEBAR_FALLBACK_PREVIEW])
  })

  it('renders second row from createdAt in dd.MM.yy HH:mm format', () => {
    const thread = createThread({
      id: 'thread-created-at',
      createdAt: '2026-02-19T08:15:00.000Z',
      updatedAt: '2026-02-21T07:30:00.000Z',
      messages: [createMessage({ role: 'assistant', content: 'Answer text' })],
    })

    const { container } = renderSidebar([thread])
    const metaRow = container.querySelector('.chat-thread-item__meta')

    expect(metaRow?.textContent?.trim()).toBe('19.02.26 09:15')
  })

  it('calls onSelectThread on click and keeps active class for activeThreadId', () => {
    const firstThread = createThread({
      id: 'thread-active',
      updatedAt: '2026-02-21T07:30:00.000Z',
      messages: [createMessage({ role: 'assistant', content: 'Active thread preview' })],
    })
    const secondThread = createThread({
      id: 'thread-inactive',
      updatedAt: '2026-02-21T07:00:00.000Z',
      messages: [createMessage({ role: 'assistant', content: 'Inactive thread preview' })],
    })

    const { container, onSelectThread } = renderSidebar([firstThread, secondThread], {
      activeThreadId: 'thread-active',
    })

    const buttons = [...container.querySelectorAll('.chat-thread-item')] as HTMLButtonElement[]
    expect(buttons).toHaveLength(2)
    expect(buttons[0]?.classList.contains('is-active')).toBe(true)
    expect(buttons[1]?.classList.contains('is-active')).toBe(false)

    fireEvent.click(buttons[1] as HTMLButtonElement)
    expect(onSelectThread).toHaveBeenCalledTimes(1)
    expect(onSelectThread).toHaveBeenCalledWith('thread-inactive')
  })
})
