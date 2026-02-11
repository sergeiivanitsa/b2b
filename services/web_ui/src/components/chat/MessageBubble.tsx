import type { ChatMessage } from '../../types/chat'

type MessageBubbleProps = {
  message: ChatMessage
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const className = `chat-message chat-message--${message.role}`
  const statusLabel =
    message.status === 'streaming' && message.role === 'assistant'
      ? 'Streaming'
      : message.status

  return (
    <article className={className}>
      <header className="chat-message__header">
        <span className="chat-message__role">{message.role}</span>
        <span className="chat-message__status">{statusLabel}</span>
      </header>
      <p className="chat-message__content">
        {message.content || (message.status === 'streaming' ? '...' : '')}
      </p>
    </article>
  )
}
