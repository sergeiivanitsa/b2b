export const CHAT_STORE_VERSION = 1
export const DEFAULT_THREAD_TITLE = 'New chat'

export type ChatMessageStatus = 'streaming' | 'completed' | 'error' | 'aborted'

export type ChatMessageRole = 'user' | 'assistant' | 'system'

export type ChatMessage = {
  id: string
  role: ChatMessageRole
  content: string
  status: ChatMessageStatus
  clientMessageId: string | null
  createdAt: string
}

export type ChatThread = {
  id: string
  title: string
  conversationId: string | null
  messages: ChatMessage[]
  createdAt: string
  updatedAt: string
}

export type ChatStoreState = {
  version: number
  activeThreadId: string | null
  threads: ChatThread[]
}

export function createEmptyChatState(): ChatStoreState {
  return {
    version: CHAT_STORE_VERSION,
    activeThreadId: null,
    threads: [],
  }
}
