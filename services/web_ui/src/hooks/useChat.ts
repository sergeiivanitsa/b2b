import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { toUserMessage } from '../auth/errors'
import { streamChat } from '../lib/chatStream'
import {
  appendMessage,
  buildAssistantStreamingPlaceholder,
  buildUserMessage,
  createThread,
  getActiveThread,
  loadChatState,
  saveChatState,
  setActiveThread,
  setThreadConversationId,
  updateMessage,
} from '../store/chatStore'
import { createEmptyChatState } from '../types/chat'
import type { ChatStoreState, ChatThread } from '../types/chat'

const SAVE_THROTTLE_MS = 350

type ActiveStreamState = {
  threadId: string
  assistantMessageId: string
  controller: AbortController
}

type UseChatResult = {
  chatState: ChatStoreState
  activeThread: ChatThread | null
  isStreaming: boolean
  streamError: string | null
  createNewChat: () => void
  selectThread: (threadId: string) => void
  sendMessage: (content: string) => Promise<void>
  stopGenerating: () => void
}

export function useChat(userId: number | undefined): UseChatResult {
  const [chatState, setChatState] = useState<ChatStoreState>(() =>
    userId ? loadChatState(userId) : createEmptyChatState(),
  )
  const [activeStream, setActiveStream] = useState<ActiveStreamState | null>(null)
  const [streamError, setStreamError] = useState<string | null>(null)

  const stateRef = useRef(chatState)
  const activeStreamRef = useRef<ActiveStreamState | null>(activeStream)
  const saveTimerRef = useRef<number | null>(null)
  const queuedSaveRef = useRef<{ userId: number; state: ChatStoreState } | null>(null)
  const userIdRef = useRef<number | undefined>(userId)

  useEffect(() => {
    stateRef.current = chatState
  }, [chatState])

  useEffect(() => {
    activeStreamRef.current = activeStream
  }, [activeStream])

  useEffect(() => {
    userIdRef.current = userId
  }, [userId])

  const flushSave = useCallback((stateToSave?: ChatStoreState, stateUserId?: number) => {
    if (stateToSave !== undefined && stateUserId !== undefined) {
      queuedSaveRef.current = {
        userId: stateUserId,
        state: stateToSave,
      }
    }
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current)
      saveTimerRef.current = null
    }
    if (queuedSaveRef.current === null) {
      return
    }
    saveChatState(queuedSaveRef.current.userId, queuedSaveRef.current.state)
    queuedSaveRef.current = null
  }, [])

  const scheduleSave = useCallback((stateToSave: ChatStoreState, stateUserId: number) => {
    queuedSaveRef.current = {
      userId: stateUserId,
      state: stateToSave,
    }
    if (saveTimerRef.current !== null) {
      return
    }
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null
      if (queuedSaveRef.current === null) {
        return
      }
      saveChatState(queuedSaveRef.current.userId, queuedSaveRef.current.state)
      queuedSaveRef.current = null
    }, SAVE_THROTTLE_MS)
  }, [])

  useEffect(() => {
    if (userId === undefined) {
      const emptyState = createEmptyChatState()
      stateRef.current = emptyState
      setChatState(emptyState)
      flushSave()
      setActiveStream(null)
      setStreamError(null)
      return
    }

    flushSave()
    const loaded = loadChatState(userId)
    stateRef.current = loaded
    setChatState(loaded)
    setActiveStream(null)
    setStreamError(null)
  }, [flushSave, userId])

  useEffect(() => {
    return () => {
      flushSave()
      const currentStream = activeStreamRef.current
      if (currentStream) {
        currentStream.controller.abort()
      }
    }
  }, [flushSave])

  const commitState = useCallback(
    (
      updater: (state: ChatStoreState) => ChatStoreState,
      mode: 'throttle' | 'immediate' = 'throttle',
    ): ChatStoreState => {
      const nextState = updater(stateRef.current)
      stateRef.current = nextState
      setChatState(nextState)
      if (userIdRef.current !== undefined) {
        if (mode === 'immediate') {
          flushSave(nextState, userIdRef.current)
        } else {
          scheduleSave(nextState, userIdRef.current)
        }
      }
      return nextState
    },
    [flushSave, scheduleSave],
  )

  const createNewChat = useCallback(() => {
    commitState((previousState) => createThread(previousState).state)
  }, [commitState])

  const selectThread = useCallback(
    (threadId: string) => {
      commitState((previousState) => setActiveThread(previousState, threadId))
    },
    [commitState],
  )

  const stopGenerating = useCallback(() => {
    const currentStream = activeStreamRef.current
    if (!currentStream) {
      return
    }
    currentStream.controller.abort()
  }, [])

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) {
        return
      }
      if (activeStreamRef.current) {
        return
      }

      setStreamError(null)

      let requestThreadId = ''
      let requestConversationId: string | null = null
      let assistantMessageId = ''
      let clientMessageId = ''

      commitState((previousState) => {
        let nextState = previousState
        let targetThreadId = nextState.activeThreadId

        if (
          !targetThreadId ||
          !nextState.threads.some((thread) => thread.id === targetThreadId)
        ) {
          const created = createThread(nextState)
          nextState = created.state
          targetThreadId = created.threadId
        }

        const activeThread = nextState.threads.find((thread) => thread.id === targetThreadId)
        requestThreadId = targetThreadId
        requestConversationId = activeThread?.conversationId ?? null

        const userMessage = buildUserMessage(content)
        clientMessageId = userMessage.clientMessageId ?? userMessage.id
        const assistantMessage = buildAssistantStreamingPlaceholder()
        assistantMessageId = assistantMessage.id

        nextState = appendMessage(nextState, targetThreadId, userMessage, {
          touchUpdatedAt: true,
        })
        nextState = appendMessage(nextState, targetThreadId, assistantMessage, {
          touchUpdatedAt: false,
        })
        return nextState
      })

      const controller = new AbortController()
      const streamState: ActiveStreamState = {
        threadId: requestThreadId,
        assistantMessageId,
        controller,
      }
      activeStreamRef.current = streamState
      setActiveStream(streamState)

      const payload = {
        client_message_id: clientMessageId,
        content,
        stream: true as const,
        ...(requestConversationId !== null
          ? { conversation_id: requestConversationId }
          : {}),
      }

      try {
        await streamChat(payload, {
          signal: controller.signal,
          onDelta: (text) => {
            if (!text) {
              return
            }
            commitState(
              (previousState) =>
                updateMessage(
                  previousState,
                  requestThreadId,
                  assistantMessageId,
                  (message) => ({
                    ...message,
                    content: `${message.content}${text}`,
                    status: 'streaming',
                  }),
                  { touchUpdatedAt: false },
                ),
              'throttle',
            )
          },
          onFinal: (data) => {
            commitState((previousState) => {
              let nextState = updateMessage(
                previousState,
                requestThreadId,
                assistantMessageId,
                (message) => ({
                  ...message,
                  content: data.text || message.content,
                  status: 'completed',
                }),
                { touchUpdatedAt: true },
              )
              if (data.conversation_id !== undefined) {
                nextState = setThreadConversationId(
                  nextState,
                  requestThreadId,
                  data.conversation_id,
                  { touchUpdatedAt: false },
                )
              }
              return nextState
            }, 'immediate')
          },
          onError: (data) => {
            commitState(
              (previousState) =>
                updateMessage(
                  previousState,
                  requestThreadId,
                  assistantMessageId,
                  (message) => ({
                    ...message,
                    status: 'error',
                  }),
                  { touchUpdatedAt: true },
                ),
              'immediate',
            )
            if (data.message) {
              setStreamError(data.message)
            } else if (data.code) {
              setStreamError(data.code.replace(/_/g, ' '))
            } else {
              setStreamError('Streaming failed.')
            }
          },
        })
      } catch (error) {
        const isAbort =
          error instanceof DOMException && error.name === 'AbortError'
        if (isAbort) {
          commitState(
            (previousState) =>
              updateMessage(
                previousState,
                requestThreadId,
                assistantMessageId,
                (message) => ({
                  ...message,
                  status: 'aborted',
                }),
                { touchUpdatedAt: true },
              ),
            'immediate',
          )
        } else {
          commitState(
            (previousState) =>
              updateMessage(
                previousState,
                requestThreadId,
                assistantMessageId,
                (message) => ({
                  ...message,
                  status: 'error',
                }),
                { touchUpdatedAt: true },
              ),
            'immediate',
          )
          setStreamError(toUserMessage(error, 'Network error during streaming.'))
        }
      } finally {
        activeStreamRef.current = null
        setActiveStream(null)
      }
    },
    [commitState],
  )

  const activeThread = useMemo(() => getActiveThread(chatState), [chatState])

  return {
    chatState,
    activeThread,
    isStreaming: activeStream !== null,
    streamError,
    createNewChat,
    selectThread,
    sendMessage,
    stopGenerating,
  }
}
