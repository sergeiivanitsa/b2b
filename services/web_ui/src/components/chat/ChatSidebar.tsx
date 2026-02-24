import { useMemo } from 'react'

import { CHAT_UI_TEXT } from '../../constants/chatUiText'
import type { ChatThread } from '../../types/chat'
import {
  buildChatSidebarGroups,
  sortThreadsByUpdatedAtDesc,
} from './chatSidebarViewModel'

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
  const groupedThreads = useMemo(() => {
    const sortedThreads = sortThreadsByUpdatedAtDesc(threads)
    return buildChatSidebarGroups(sortedThreads)
  }, [threads])

  return (
    <aside className="chat-sidebar">
      <div className="chat-sidebar__header">
        <h2 className="chat-sidebar__title">{CHAT_UI_TEXT.sidebarTitle}</h2>
        <button className="button button--secondary" onClick={onCreateThread} type="button">
          {CHAT_UI_TEXT.newDialog}
        </button>
      </div>

      <ul className="chat-sidebar__list">
        {groupedThreads.map((group) => (
          <li key={group.key} className="chat-sidebar__group">
            <p className="chat-sidebar__group-title">{group.label}</p>
            {group.items.map((item) => (
              <button
                key={item.threadId}
                type="button"
                className={`chat-thread-item ${item.threadId === activeThreadId ? 'is-active' : ''}`}
                onClick={() => onSelectThread(item.threadId)}
              >
                <span className="chat-thread-item__title">{item.preview}</span>
                <span className="chat-thread-item__meta">{item.createdAtLabel}</span>
              </button>
            ))}
          </li>
        ))}
      </ul>
    </aside>
  )
}
