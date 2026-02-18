import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatComposer } from './ChatComposer'

type RenderOptions = {
  isStreaming?: boolean
}

function renderComposer(options: RenderOptions = {}) {
  const onSendMessage = vi.fn<(content: string) => void>()
  const onStopGenerating = vi.fn<() => void>()

  render(
    <ChatComposer
      isStreaming={options.isStreaming ?? false}
      onSendMessage={onSendMessage}
      onStopGenerating={onStopGenerating}
    />,
  )

  return { onSendMessage, onStopGenerating }
}

describe('ChatComposer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('disables send button when input is empty or whitespace', () => {
    renderComposer()

    const textarea = screen.getByPlaceholderText('Отправьте сообщение...') as HTMLTextAreaElement
    const button = screen.getByRole('button', { name: 'Send message' }) as HTMLButtonElement

    expect(button.disabled).toBe(true)

    fireEvent.change(textarea, { target: { value: '   ' } })
    expect(button.disabled).toBe(true)
  })

  it('sends trimmed message on click and clears textarea', () => {
    const { onSendMessage } = renderComposer()

    const textarea = screen.getByPlaceholderText('Отправьте сообщение...') as HTMLTextAreaElement
    const button = screen.getByRole('button', { name: 'Send message' }) as HTMLButtonElement

    fireEvent.change(textarea, { target: { value: '  hello  ' } })
    expect(button.disabled).toBe(false)

    fireEvent.click(button)

    expect(onSendMessage).toHaveBeenCalledTimes(1)
    expect(onSendMessage).toHaveBeenCalledWith('hello')
    expect(textarea.value).toBe('')
  })

  it('sends on Enter and does not send on Shift+Enter', () => {
    const { onSendMessage } = renderComposer()

    const textarea = screen.getByPlaceholderText('Отправьте сообщение...') as HTMLTextAreaElement

    fireEvent.change(textarea, { target: { value: 'line one' } })
    fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' })

    expect(onSendMessage).toHaveBeenCalledTimes(1)
    expect(onSendMessage).toHaveBeenCalledWith('line one')

    fireEvent.change(textarea, { target: { value: 'line two' } })
    fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter', shiftKey: true })

    expect(onSendMessage).toHaveBeenCalledTimes(1)
  })

  it('switches button to stop mode while streaming', () => {
    const { onSendMessage, onStopGenerating } = renderComposer({ isStreaming: true })

    const stopButton = screen.getByRole('button', {
      name: 'Stop generating',
    }) as HTMLButtonElement
    const textarea = screen.getByPlaceholderText('Отправьте сообщение...') as HTMLTextAreaElement

    expect(stopButton.disabled).toBe(false)
    expect(textarea.disabled).toBe(true)

    fireEvent.click(stopButton)

    expect(onStopGenerating).toHaveBeenCalledTimes(1)
    expect(onSendMessage).not.toHaveBeenCalled()
  })
})
