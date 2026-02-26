import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useAutoScroll } from '../../hooks/useAutoScroll'
import { CHAT_UI_TEXT } from '../../constants/chatUiText'
import { DEFAULT_THREAD_TITLE, type ChatThread } from '../../types/chat'
import { ChatWindow } from './ChatWindow'

vi.mock('../../hooks/useAutoScroll', () => ({
  useAutoScroll: vi.fn(() => ({
    containerRef: { current: null },
    bottomRef: { current: null },
    showScrollButton: false,
    scrollToBottom: vi.fn(),
  })),
}))

function createThread(overrides: Partial<ChatThread> = {}): ChatThread {
  return {
    id: overrides.id ?? 'thread-id',
    title: overrides.title ?? DEFAULT_THREAD_TITLE,
    conversationId: overrides.conversationId ?? null,
    messages: overrides.messages ?? [],
    createdAt: overrides.createdAt ?? '2026-02-20T10:00:00.000Z',
    updatedAt: overrides.updatedAt ?? '2026-02-20T10:00:00.000Z',
  }
}

describe('ChatWindow', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('renders localized empty-state title and prompt for a new thread', () => {
    const thread = createThread({
      title: DEFAULT_THREAD_TITLE,
      messages: [],
    })

    render(<ChatWindow thread={thread} />)

    expect(screen.getByRole('heading', { name: DEFAULT_THREAD_TITLE })).toBeTruthy()
    expect(screen.getByText(CHAT_UI_TEXT.emptyStartPrompt)).toBeTruthy()
    expect(screen.queryByText('Start by sending your first message.')).toBeNull()
  })

  it('renders icon-only scroll-to-bottom button with aria-label', () => {
    const scrollToBottom = vi.fn()
    vi.mocked(useAutoScroll).mockReturnValue({
      containerRef: { current: null },
      bottomRef: { current: null },
      showScrollButton: true,
      scrollToBottom,
    })

    const thread = createThread({
      messages: [
        {
          id: 'message-1',
          role: 'assistant',
          content: 'Long answer',
          status: 'completed',
          clientMessageId: null,
          createdAt: '2026-02-20T10:01:00.000Z',
        },
      ],
    })

    render(<ChatWindow thread={thread} />)

    const button = screen.getByRole('button', {
      name: '\u041f\u0440\u043e\u043a\u0440\u0443\u0442\u0438\u0442\u044c \u0432\u043d\u0438\u0437',
    })
    expect(button.textContent?.trim()).toBe('')

    const icon = button.querySelector('img') as HTMLImageElement | null
    expect(icon?.getAttribute('src')).toBe('/arrow.webp')

    fireEvent.click(button)
    expect(scrollToBottom).toHaveBeenCalledWith('smooth')
    expect(screen.queryByText('Scroll to bottom')).toBeNull()
  })
})
