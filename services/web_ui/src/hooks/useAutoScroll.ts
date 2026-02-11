import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { RefObject } from 'react'

const NEAR_BOTTOM_THRESHOLD_PX = 80

type UseAutoScrollResult = {
  containerRef: RefObject<HTMLElement | null>
  bottomRef: RefObject<HTMLDivElement | null>
  showScrollButton: boolean
  scrollToBottom: (behavior?: ScrollBehavior) => void
}

function isNearBottom(container: HTMLElement): boolean {
  const remaining = container.scrollHeight - container.scrollTop - container.clientHeight
  return remaining <= NEAR_BOTTOM_THRESHOLD_PX
}

export function useAutoScroll(messageCount: number, threadId: string | null): UseAutoScrollResult {
  const containerRef = useRef<HTMLElement | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const [nearBottom, setNearBottom] = useState(true)

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    bottomRef.current?.scrollIntoView({
      behavior,
      block: 'end',
    })
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!container) {
      return
    }

    const onScroll = () => {
      setNearBottom(isNearBottom(container))
    }

    setNearBottom(isNearBottom(container))
    container.addEventListener('scroll', onScroll)
    return () => {
      container.removeEventListener('scroll', onScroll)
    }
  }, [threadId])

  useEffect(() => {
    if (!nearBottom) {
      return
    }
    scrollToBottom('smooth')
  }, [messageCount, nearBottom, scrollToBottom, threadId])

  const showScrollButton = useMemo(() => messageCount > 0 && !nearBottom, [messageCount, nearBottom])

  return {
    containerRef,
    bottomRef,
    showScrollButton,
    scrollToBottom,
  }
}
