import { useState } from 'react'
import type { FormEvent } from 'react'

type ChatComposerProps = {
  isStreaming: boolean
  onSendMessage: (content: string) => void
  onStopGenerating: () => void
}

export function ChatComposer({
  isStreaming,
  onSendMessage,
  onStopGenerating,
}: ChatComposerProps) {
  const [content, setContent] = useState('')
  const normalized = content.trim()
  const canSend = normalized.length > 0 && !isStreaming

  function submitMessage() {
    if (!normalized) {
      return
    }
    onSendMessage(normalized)
    setContent('')
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isStreaming) {
      return
    }
    submitMessage()
  }

  return (
    <form className="chat-composer" onSubmit={onSubmit}>
      <div className="chat-composer__bubble">
        <textarea
          className="chat-composer__input"
          value={content}
          onChange={(event) => setContent(event.target.value)}
          onKeyDown={(event) => {
            const isComposing = event.nativeEvent.isComposing
            if (event.key !== 'Enter' || event.shiftKey || isComposing) {
              return
            }
            event.preventDefault()
            submitMessage()
          }}
          rows={3}
          placeholder="Send a message..."
          disabled={isStreaming}
        />
        <button
          className={`chat-composer__action ${isStreaming ? 'is-stop' : 'is-send'}`}
          type={isStreaming ? 'button' : 'submit'}
          onClick={isStreaming ? onStopGenerating : undefined}
          disabled={isStreaming ? false : !canSend}
          aria-label={isStreaming ? 'Stop generating' : 'Send message'}
        >
          {isStreaming ? (
            <svg
              className="chat-composer__icon-stop"
              viewBox="0 0 12 12"
              aria-hidden="true"
              focusable="false"
            >
              <rect x="2" y="2" width="8" height="8" rx="1" />
            </svg>
          ) : (
            <svg
              className="chat-composer__icon-send"
              viewBox="0 0 24 24"
              aria-hidden="true"
              focusable="false"
            >
              <path d="M12 19V5" />
              <path d="m6 11 6-6 6 6" />
            </svg>
          )}
        </button>
      </div>
    </form>
  )
}
