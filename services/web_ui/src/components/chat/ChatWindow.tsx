import type { ChatThread } from '../../types/chat'
import { MessageBubble } from './MessageBubble'

type ChatWindowProps = {
  thread: ChatThread | null
}

export function ChatWindow({ thread }: ChatWindowProps) {
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
    <section className="chat-window">
      {thread.messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
    </section>
  )
}
