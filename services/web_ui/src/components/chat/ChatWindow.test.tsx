import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { CHAT_UI_TEXT } from '../../constants/chatUiText'
import { DEFAULT_THREAD_TITLE, type ChatThread } from '../../types/chat'
import { ChatWindow } from './ChatWindow'

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
})
