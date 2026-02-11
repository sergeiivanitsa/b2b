import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ChatShell } from '../components/chat/ChatShell'
import { toUserMessage } from '../auth/errors'
import { useAuth } from '../auth/useAuth'
import { useChat } from '../hooks/useChat'

export function ChatPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [isSubmittingLogout, setIsSubmittingLogout] = useState(false)
  const [logoutError, setLogoutError] = useState<string | null>(null)
  const {
    chatState,
    activeThread,
    isStreaming,
    streamError,
    createNewChat,
    selectThread,
    sendMessage,
    stopGenerating,
  } = useChat(user?.id)

  async function onLogout() {
    setIsSubmittingLogout(true)
    setLogoutError(null)
    try {
      if (isStreaming) {
        stopGenerating()
      }
      await logout()
      navigate('/login', { replace: true })
    } catch (logoutError) {
      setLogoutError(toUserMessage(logoutError, 'Could not log out right now.'))
    } finally {
      setIsSubmittingLogout(false)
    }
  }

  if (!user) {
    return (
      <main className="screen">
        <section className="card">
          <h1 className="card__title">Loading chat</h1>
          <p className="card__subtitle">Please wait...</p>
        </section>
      </main>
    )
  }

  return (
    <ChatShell
      user={user}
      threads={chatState.threads}
      activeThreadId={chatState.activeThreadId}
      activeThread={activeThread}
      isStreaming={isStreaming}
      streamError={streamError}
      isLoggingOut={isSubmittingLogout}
      logoutError={logoutError}
      onCreateThread={createNewChat}
      onSelectThread={selectThread}
      onSendMessage={(content) => {
        void sendMessage(content)
      }}
      onStopGenerating={stopGenerating}
      onLogout={onLogout}
    />
  )
}
