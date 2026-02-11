import type { ChatThread } from '../../types/chat'
import { useAutoScroll } from '../../hooks/useAutoScroll'
import { MessageBubble } from './MessageBubble'

type ChatWindowProps = {
  thread: ChatThread | null
}

export function ChatWindow({ thread }: ChatWindowProps) {
  const messageCount = thread?.messages.length ?? 0
  const { containerRef, bottomRef, showScrollButton, scrollToBottom } = useAutoScroll(
    messageCount,
    thread?.id ?? null,
  )

  if (!thread) {
    return (
      <section className="chat-window chat-window--empty">
        <h2>No chat selected</h2>
        <p>Create a new chat in the left panel to begin.</p>
      </section>
    )
  }

  if (thread.messages.length === 0) {
    return (
      <section className="chat-window chat-window--empty">
        <h2>{thread.title}</h2>
        <p>Start by sending your first message.</p>
      </section>
    )
  }

  return (
    <section className="chat-window-shell">
      <section className="chat-window" ref={containerRef}>
        {thread.messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={bottomRef} aria-hidden />
      </section>
      {showScrollButton ? (
        <button
          className="chat-scroll-bottom button button--secondary"
          type="button"
          onClick={() => scrollToBottom('smooth')}
        >
          Scroll to bottom
        </button>
      ) : null}
    </section>
  )
}
