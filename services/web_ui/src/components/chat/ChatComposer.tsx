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

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalized = content.trim()
    if (!normalized) {
      return
    }
    onSendMessage(normalized)
    setContent('')
  }

  return (
    <form className="chat-composer" onSubmit={onSubmit}>
      <textarea
        className="chat-composer__input"
        value={content}
        onChange={(event) => setContent(event.target.value)}
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
