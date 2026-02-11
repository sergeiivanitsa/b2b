import type { ChatThread } from '../../types/chat'

type ChatSidebarProps = {
  threads: ChatThread[]
  activeThreadId: string | null
  onCreateThread: () => void
  onSelectThread: (threadId: string) => void
}

export function ChatSidebar({
  threads,
  activeThreadId,
  onCreateThread,
  onSelectThread,
}: ChatSidebarProps) {
  return (
    <aside className="chat-sidebar">
      <div className="chat-sidebar__header">
        <h2 className="chat-sidebar__title">Chats</h2>
        <button className="button button--secondary" onClick={onCreateThread} type="button">
          New chat
        </button>
      </div>

      <ul className="chat-sidebar__list">
        {threads.map((thread) => (
          <li key={thread.id}>
            <button
              type="button"
              className={`chat-thread-item ${thread.id === activeThreadId ? 'is-active' : ''}`}
              onClick={() => onSelectThread(thread.id)}
            >
              <span className="chat-thread-item__title">{thread.title}</span>
              <span className="chat-thread-item__meta">
                {new Date(thread.updatedAt).toLocaleString()}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}
