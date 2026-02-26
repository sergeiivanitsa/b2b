import { Link } from 'react-router-dom'

import type { AuthUser } from '../../auth/types'
import { CHAT_UI_TEXT } from '../../constants/chatUiText'
import type { ChatThread } from '../../types/chat'
import { ChatComposer } from './ChatComposer'
import { ChatSidebar } from './ChatSidebar'
import { ChatWindow } from './ChatWindow'

type ChatShellProps = {
  user: AuthUser
  threads: ChatThread[]
  activeThreadId: string | null
  activeThread: ChatThread | null
  isStreaming: boolean
  streamError: string | null
  isLoggingOut: boolean
  logoutError: string | null
  onCreateThread: () => void
  onSelectThread: (threadId: string) => void
  onSendMessage: (content: string) => void
  onStopGenerating: () => void
  onLogout: () => void
}

const CREDITS_NUMBER_FORMATTER = new Intl.NumberFormat('ru-RU')

export function ChatShell({
  user,
  threads,
  activeThreadId,
  activeThread,
  isStreaming,
  streamError,
  isLoggingOut,
  logoutError,
  onCreateThread,
  onSelectThread,
  onSendMessage,
  onStopGenerating,
  onLogout,
}: ChatShellProps) {
  const orgId = user.org_id ?? user.company_id
  const canAccessAdmin = user.role === 'owner' || user.role === 'admin'
  const displayName = buildUserDisplayName(user)
  const companyName = normalizeOptionalText(user.company_name)
  const creditsValue = normalizeCredits(user.remaining_credits)
  const creditsLabel = `${CHAT_UI_TEXT.creditsLabel}: ${CREDITS_NUMBER_FORMATTER.format(creditsValue)}`
  const subtitle = companyName ? `${companyName} • ${creditsLabel}` : creditsLabel

  return (
    <main className="chat-shell">
      <ChatSidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onCreateThread={onCreateThread}
        onSelectThread={onSelectThread}
      />

      <section className="chat-main">
        <header className="chat-main__header">
          <div className="chat-main__identity">
            <strong>{displayName}</strong>
            <span>{subtitle}</span>
          </div>
          <div className="chat-main__actions">
            {canAccessAdmin && orgId ? (
              <Link to={`/org/${orgId}/admin`} className="button button--secondary">
                {CHAT_UI_TEXT.adminAction}
              </Link>
            ) : null}
            <button
              type="button"
              className="button button--secondary"
              onClick={onLogout}
              disabled={isLoggingOut}
            >
              {isLoggingOut ? 'Logging out...' : 'Logout'}
            </button>
          </div>
        </header>

        {logoutError ? <p className="message message--error">{logoutError}</p> : null}
        {streamError ? <p className="message message--error">{streamError}</p> : null}

        <ChatWindow thread={activeThread} />
        <ChatComposer
          isStreaming={isStreaming}
          onSendMessage={onSendMessage}
          onStopGenerating={onStopGenerating}
        />
      </section>
    </main>
  )
}

function buildUserDisplayName(user: AuthUser): string {
  const firstName = normalizeOptionalText(user.first_name)
  const lastName = normalizeOptionalText(user.last_name)
  const fullName = `${firstName} ${lastName}`.trim()
  return fullName || user.email
}

function normalizeOptionalText(value: string | null | undefined): string {
  if (typeof value !== 'string') {
    return ''
  }
  return value.trim()
}

function normalizeCredits(value: number | undefined): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return 0
  }
  return Math.max(0, Math.trunc(value))
}

