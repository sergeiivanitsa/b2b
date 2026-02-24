import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthUser } from '../../auth/types'
import { CHAT_UI_TEXT } from '../../constants/chatUiText'
import type { ChatThread } from '../../types/chat'

vi.mock('./ChatSidebar', () => ({
  ChatSidebar: () => <aside data-testid="chat-sidebar-mock" />,
}))

vi.mock('./ChatWindow', () => ({
  ChatWindow: () => <section data-testid="chat-window-mock" />,
}))

vi.mock('./ChatComposer', () => ({
  ChatComposer: () => <form data-testid="chat-composer-mock" />,
}))

import { ChatShell } from './ChatShell'

type RenderOptions = {
  user?: Partial<AuthUser>
  threads?: ChatThread[]
}

function createUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 10,
    email: 'user@example.com',
    role: 'owner',
    org_id: 7,
    company_id: 7,
    is_superadmin: false,
    is_active: true,
    first_name: null,
    last_name: null,
    company_name: null,
    remaining_credits: 0,
    ...overrides,
  }
}

function renderShell(options: RenderOptions = {}) {
  const onCreateThread = vi.fn<() => void>()
  const onSelectThread = vi.fn<(threadId: string) => void>()
  const onSendMessage = vi.fn<(content: string) => void>()
  const onStopGenerating = vi.fn<() => void>()
  const onLogout = vi.fn<() => void>()

  const user = createUser(options.user)

  render(
    <MemoryRouter>
      <ChatShell
        user={user}
        threads={options.threads ?? []}
        activeThreadId={null}
        activeThread={null}
        isStreaming={false}
        streamError={null}
        isLoggingOut={false}
        logoutError={null}
        onCreateThread={onCreateThread}
        onSelectThread={onSelectThread}
        onSendMessage={onSendMessage}
        onStopGenerating={onStopGenerating}
        onLogout={onLogout}
      />
    </MemoryRouter>,
  )

  return {
    onCreateThread,
    onSelectThread,
    onSendMessage,
    onStopGenerating,
    onLogout,
  }
}

describe('ChatShell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('shows full name when first and last name are available', () => {
    renderShell({
      user: {
        first_name: 'Иван',
        last_name: 'Петров',
      },
    })

    expect(screen.getByText('Иван Петров')).toBeTruthy()
  })

  it('falls back to email when first and last name are empty', () => {
    renderShell({
      user: {
        email: 'fallback@example.com',
        first_name: '   ',
        last_name: null,
      },
    })

    expect(screen.getByText('fallback@example.com')).toBeTruthy()
  })

  it('renders company and remaining credits in header subtitle', () => {
    renderShell({
      user: {
        company_name: 'ООО Ромашка',
        remaining_credits: 42,
      },
    })

    expect(
      screen.getByText(
        (content) =>
          content.includes('ООО Ромашка') &&
          content.includes(`${CHAT_UI_TEXT.creditsLabel}: 42`),
      ),
    ).toBeTruthy()
  })

  it('does not render connectivity badge copy', () => {
    renderShell()

    expect(screen.queryByText('Connected')).toBeNull()
    expect(screen.queryByText('Offline')).toBeNull()
  })

  it('renders localized admin action for admin-capable users', () => {
    renderShell({
      user: {
        role: 'owner',
        org_id: 7,
      },
    })

    const adminLink = screen.getByRole('link', {
      name: CHAT_UI_TEXT.adminAction,
    }) as HTMLAnchorElement

    expect(adminLink.getAttribute('href')).toBe('/org/7/admin')
  })

  it('exposes logout action with aria-label "Выйти"', () => {
    renderShell()

    const logoutButton = screen.getByRole('button', {
      name: 'Выйти',
    }) as HTMLButtonElement

    expect(logoutButton.getAttribute('aria-label')).toBe('Выйти')
  })
})
