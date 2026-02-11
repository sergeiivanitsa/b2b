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

  function submitMessage() {
    const normalized = content.trim()
    if (!normalized) {
      return
    }
    onSendMessage(normalized)
    setContent('')
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submitMessage()
  }

  return (
    <form className="chat-composer" onSubmit={onSubmit}>
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
      <div className="chat-composer__actions">
        <button className="button" type="submit" disabled={isStreaming}>
          Send
        </button>
        <button
          className="button button--secondary"
          type="button"
          onClick={onStopGenerating}
          disabled={!isStreaming}
        >
          Stop generating
        </button>
      </div>
    </form>
  )
}
