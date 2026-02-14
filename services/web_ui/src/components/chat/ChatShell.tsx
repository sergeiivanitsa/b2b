import { Link } from 'react-router-dom'

import type { AuthUser } from '../../auth/types'
import { useConnectivity } from '../../hooks/useConnectivity'
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
  const isOnline = useConnectivity()
  const orgId = user.org_id ?? user.company_id
  const canAccessAdmin = user.role === 'owner' || user.role === 'admin'

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
            <strong>{user.email}</strong>
            <span>
              role: {user.role} | org_id: {orgId ?? '-'} | active:{' '}
              {String(user.is_active)}
            </span>
          </div>
          <div className="chat-main__actions">
            <span
              className={`connectivity-badge ${isOnline ? 'is-online' : 'is-offline'}`}
              aria-live="polite"
            >
              {isOnline ? 'Connected' : 'Offline'}
            </span>
            {canAccessAdmin && orgId ? (
              <Link to={`/org/${orgId}/admin`} className="button button--secondary">
                Admin
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
