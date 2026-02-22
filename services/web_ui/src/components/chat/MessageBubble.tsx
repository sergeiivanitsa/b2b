import { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

import type { ChatMessage } from '../../types/chat'

type MessageBubbleProps = {
  message: ChatMessage
}

const COPIED_TOAST_MS = 1400
const HAS_CODE_BLOCK_PATTERN = /```(?:[\w+-]+)?\s*\n?([\s\S]*?)```/
const CODE_BLOCK_PATTERN = /```(?:[\w+-]+)?\s*\n?([\s\S]*?)```/g

export function MessageBubble({ message }: MessageBubbleProps) {
  const [isCopiedToastVisible, setIsCopiedToastVisible] = useState(false)

  const className = `chat-message chat-message--${message.role}`
  const statusLabel =
    message.status === 'streaming' && message.role === 'assistant'
      ? 'Streaming'
      : message.status
  const hasAssistantCodeBlock = useMemo(
    () => message.role === 'assistant' && HAS_CODE_BLOCK_PATTERN.test(message.content),
    [message.content, message.role],
  )
  const extractedCodeText = useMemo(() => extractCodeForCopy(message.content), [message.content])

  useEffect(() => {
    if (!isCopiedToastVisible) {
      return
    }
    const timeout = window.setTimeout(() => {
      setIsCopiedToastVisible(false)
    }, COPIED_TOAST_MS)
    return () => {
      window.clearTimeout(timeout)
    }
  }, [isCopiedToastVisible])

  async function copyMessage() {
    try {
      await copyText(message.content)
      setIsCopiedToastVisible(true)
    } catch {
      setIsCopiedToastVisible(false)
    }
  }

  async function copyCode() {
    if (!extractedCodeText) {
      return
    }
    try {
      await copyText(extractedCodeText)
      setIsCopiedToastVisible(true)
    } catch {
      setIsCopiedToastVisible(false)
    }
  }

  return (
    <article className={className}>
      <header className="chat-message__header">
        <span className="chat-message__role">{message.role}</span>
        <div className="chat-message__meta">
          <span className="chat-message__status">{statusLabel}</span>
        </div>
      </header>
      <div className="chat-message__content">
        {message.role === 'assistant' ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeSanitize]}
            components={{
              a: ({ ...props }) => (
                <a {...props} target="_blank" rel="noopener noreferrer" />
              ),
            }}
          >
            {message.content || (message.status === 'streaming' ? '...' : '')}
          </ReactMarkdown>
        ) : (
          <p>{message.content || (message.status === 'streaming' ? '...' : '')}</p>
        )}
      </div>
      <div className="chat-message__actions">
        <button className="chat-message__copy" type="button" onClick={() => void copyMessage()}>
          Copy message
        </button>
        {hasAssistantCodeBlock ? (
          <button className="chat-message__copy" type="button" onClick={() => void copyCode()}>
            Copy code
          </button>
        ) : null}
      </div>
      {isCopiedToastVisible ? <div className="chat-message__toast">Copied</div> : null}
    </article>
  )
}

async function copyText(value: string): Promise<void> {
  if (typeof navigator === 'undefined' || !navigator.clipboard?.writeText) {
    throw new Error('Clipboard is unavailable.')
  }
  await navigator.clipboard.writeText(value)
}

function extractCodeForCopy(content: string): string {
  const codeBlocks: string[] = []
  let match = CODE_BLOCK_PATTERN.exec(content)
  while (match) {
    codeBlocks.push(match[1]?.replace(/\n$/, '') ?? '')
    match = CODE_BLOCK_PATTERN.exec(content)
  }
  CODE_BLOCK_PATTERN.lastIndex = 0
  return codeBlocks.filter(Boolean).join('\n\n')
}
