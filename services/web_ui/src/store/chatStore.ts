import {
  CHAT_STORE_VERSION,
  DEFAULT_THREAD_TITLE,
  createEmptyChatState,
} from '../types/chat'
import type { ChatMessage, ChatStoreState, ChatThread } from '../types/chat'

const CHAT_STORAGE_PREFIX = 'chat_history'
type UpdateThreadOptions = {
  touchUpdatedAt?: boolean
}

export function loadChatState(userId: number): ChatStoreState {
  if (typeof window === 'undefined') {
    return createEmptyChatState()
  }
  try {
    const raw = window.localStorage.getItem(getChatStorageKey(userId))
    if (!raw) {
      return createEmptyChatState()
    }
    const parsed = JSON.parse(raw) as Partial<ChatStoreState>
    if (parsed.version !== CHAT_STORE_VERSION || !Array.isArray(parsed.threads)) {
      return createEmptyChatState()
    }

    const threads = parsed.threads
      .filter(isValidThread)
      .sort((a, b) => compareByUpdatedAtDesc(a.updatedAt, b.updatedAt))

    const activeThreadId =
      parsed.activeThreadId && threads.some((thread) => thread.id === parsed.activeThreadId)
        ? parsed.activeThreadId
        : threads[0]?.id ?? null

    return {
      version: CHAT_STORE_VERSION,
      activeThreadId,
      threads,
    }
  } catch {
    return createEmptyChatState()
  }
}

export function saveChatState(userId: number, state: ChatStoreState): void {
  if (typeof window === 'undefined') {
    return
  }
  const serializableState: ChatStoreState = {
    version: CHAT_STORE_VERSION,
    activeThreadId: state.activeThreadId,
    threads: state.threads,
  }
  window.localStorage.setItem(
    getChatStorageKey(userId),
    JSON.stringify(serializableState),
  )
}

export function createThread(
  state: ChatStoreState,
  title: string = DEFAULT_THREAD_TITLE,
): { state: ChatStoreState; threadId: string } {
  const now = nowIso()
  const thread: ChatThread = {
    id: generateId(),
    title,
    conversationId: null,
    messages: [],
    createdAt: now,
    updatedAt: now,
  }
  const threads = [thread, ...state.threads].sort((a, b) =>
    compareByUpdatedAtDesc(a.updatedAt, b.updatedAt),
  )
  return {
    threadId: thread.id,
    state: {
      ...state,
      activeThreadId: thread.id,
      threads,
    },
  }
}

export function setActiveThread(
  state: ChatStoreState,
  threadId: string,
): ChatStoreState {
  if (!state.threads.some((thread) => thread.id === threadId)) {
    return state
  }
  return {
    ...state,
    activeThreadId: threadId,
  }
}

export function appendMessage(
  state: ChatStoreState,
  threadId: string,
  message: ChatMessage,
  options: UpdateThreadOptions = {},
): ChatStoreState {
  return updateThread(
    state,
    threadId,
    (thread, updatedAt) => ({
      ...thread,
      updatedAt,
      messages: [...thread.messages, message],
    }),
    options,
  )
}

export function updateMessage(
  state: ChatStoreState,
  threadId: string,
  messageId: string,
  updater: (message: ChatMessage) => ChatMessage,
  options: UpdateThreadOptions = {},
): ChatStoreState {
  return updateThread(
    state,
    threadId,
    (thread, updatedAt) => {
      let changed = false
      const messages = thread.messages.map((message) => {
        if (message.id !== messageId) {
          return message
        }
        changed = true
        return updater(message)
      })
      if (!changed) {
        return thread
      }
      return {
        ...thread,
        updatedAt,
        messages,
      }
    },
    options,
  )
}

export function setThreadConversationId(
  state: ChatStoreState,
  threadId: string,
  conversationId: string | null,
  options: UpdateThreadOptions = {},
): ChatStoreState {
  return updateThread(
    state,
    threadId,
    (thread, updatedAt) => {
      if (thread.conversationId === conversationId) {
        return thread
      }
      return {
        ...thread,
        updatedAt,
        conversationId,
      }
    },
    options,
  )
}

export function getActiveThread(state: ChatStoreState): ChatThread | null {
  if (!state.activeThreadId) {
    return null
  }
  return state.threads.find((thread) => thread.id === state.activeThreadId) ?? null
}

export function buildUserMessage(content: string): ChatMessage {
  return {
    id: generateId(),
    role: 'user',
    content,
    status: 'completed',
    clientMessageId: generateId(),
    createdAt: nowIso(),
  }
}

export function buildAssistantStreamingPlaceholder(): ChatMessage {
  return {
    id: generateId(),
    role: 'assistant',
    content: '',
    status: 'streaming',
    clientMessageId: null,
    createdAt: nowIso(),
  }
}

function updateThread(
  state: ChatStoreState,
  threadId: string,
  updater: (thread: ChatThread, updatedAt: string) => ChatThread,
  options: UpdateThreadOptions = {},
): ChatStoreState {
  const touchUpdatedAt = options.touchUpdatedAt ?? true
  let touched = false
  const updatedAt = touchUpdatedAt ? nowIso() : ''
  const nextThreads = state.threads.map((thread) => {
    if (thread.id !== threadId) {
      return thread
    }
    const nextThread = updater(thread, updatedAt || thread.updatedAt)
    if (nextThread !== thread) {
      touched = true
    }
    return nextThread
  })

  if (!touched) {
    return state
  }

  if (touchUpdatedAt) {
    nextThreads.sort((a, b) => compareByUpdatedAtDesc(a.updatedAt, b.updatedAt))
  }

  return {
    ...state,
    threads: nextThreads,
    activeThreadId: state.activeThreadId ?? threadId,
  }
}

function isValidThread(value: unknown): value is ChatThread {
  if (!value || typeof value !== 'object') {
    return false
  }
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.title === 'string' &&
    (typeof candidate.conversationId === 'string' || candidate.conversationId === null) &&
    typeof candidate.createdAt === 'string' &&
    typeof candidate.updatedAt === 'string' &&
    Array.isArray(candidate.messages)
  )
}

function compareByUpdatedAtDesc(left: string, right: string): number {
  return new Date(right).getTime() - new Date(left).getTime()
}

function getChatStorageKey(userId: number): string {
  return `${CHAT_STORAGE_PREFIX}:${userId}`
}

function nowIso(): string {
  return new Date().toISOString()
}

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}
