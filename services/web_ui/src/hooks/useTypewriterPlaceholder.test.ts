import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useTypewriterPlaceholder } from './useTypewriterPlaceholder'

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

type MatchMediaController = {
  emit: (nextMatches: boolean) => void
}

type MatchMediaListener = (event: MediaQueryListEvent) => void

const initialMatchMedia = window.matchMedia

function installMatchMediaMock(initialMatches: boolean): MatchMediaController {
  let matches = initialMatches
  const listeners = new Set<MatchMediaListener>()

  const mediaQueryList = {
    media: REDUCED_MOTION_QUERY,
    matches,
    onchange: null,
    addEventListener: (
      type: string,
      listener: EventListenerOrEventListenerObject | null,
    ) => {
      if (type !== 'change' || listener === null || typeof listener !== 'function') {
        return
      }
      listeners.add(listener as MatchMediaListener)
    },
    removeEventListener: (
      type: string,
      listener: EventListenerOrEventListenerObject | null,
    ) => {
      if (type !== 'change' || listener === null || typeof listener !== 'function') {
        return
      }
      listeners.delete(listener as MatchMediaListener)
    },
    addListener: (listener: MatchMediaListener) => {
      listeners.add(listener)
    },
    removeListener: (listener: MatchMediaListener) => {
      listeners.delete(listener)
    },
    dispatchEvent: (_event: Event) => true,
  } as MediaQueryList

  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((_query: string) => mediaQueryList),
  })

  return {
    emit: (nextMatches: boolean) => {
      matches = nextMatches
      ;(mediaQueryList as { matches: boolean }).matches = matches
      const event = {
        media: REDUCED_MOTION_QUERY,
        matches,
      } as MediaQueryListEvent
      listeners.forEach((listener) => {
        listener(event)
      })
      mediaQueryList.onchange?.call(mediaQueryList, event)
    },
  }
}

describe('useTypewriterPlaceholder', () => {
  let matchMediaController: MatchMediaController

  beforeEach(() => {
    vi.useFakeTimers()
    matchMediaController = installMatchMediaMock(false)
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()

    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: initialMatchMedia,
    })
  })

  it('types, holds, clears, and loops through phrases', () => {
    const { result } = renderHook(() =>
      useTypewriterPlaceholder({
        phrases: ['abc', 'xy'],
        typingMs: 10,
        holdMs: 30,
      }),
    )

    expect(result.current.placeholder).toBe('')

    act(() => {
      vi.advanceTimersByTime(10)
    })
    expect(result.current.placeholder).toBe('a')

    act(() => {
      vi.advanceTimersByTime(10)
    })
    expect(result.current.placeholder).toBe('ab')

    act(() => {
      vi.advanceTimersByTime(10)
    })
    expect(result.current.placeholder).toBe('abc')

    act(() => {
      vi.advanceTimersByTime(30)
    })
    expect(result.current.placeholder).toBe('')

    act(() => {
      vi.advanceTimersByTime(10)
    })
    expect(result.current.placeholder).toBe('x')

    act(() => {
      vi.advanceTimersByTime(10)
    })
    expect(result.current.placeholder).toBe('xy')

    act(() => {
      vi.advanceTimersByTime(30)
    })
    expect(result.current.placeholder).toBe('')

    act(() => {
      vi.advanceTimersByTime(10)
    })
    expect(result.current.placeholder).toBe('a')
  })

  it('pauses and resumes typing when paused changes', () => {
    const { result, rerender } = renderHook(
      ({ paused }: { paused: boolean }) =>
        useTypewriterPlaceholder({
          phrases: ['ab'],
          typingMs: 10,
          holdMs: 30,
          paused,
        }),
      {
        initialProps: { paused: false },
      },
    )

    act(() => {
      vi.advanceTimersByTime(10)
    })
    expect(result.current.placeholder).toBe('a')

    rerender({ paused: true })
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.placeholder).toBe('a')

    rerender({ paused: false })
    act(() => {
      vi.advanceTimersByTime(10)
    })
    expect(result.current.placeholder).toBe('ab')
  })

  it('returns static placeholder when disabled', () => {
    const { result } = renderHook(() =>
      useTypewriterPlaceholder({
        phrases: ['abc'],
        enabled: false,
        staticPlaceholder: 'static',
      }),
    )

    expect(result.current.placeholder).toBe('static')
    expect(result.current.isReducedMotion).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('returns static placeholder and does not start timers when reduce motion is enabled', () => {
    matchMediaController.emit(true)

    const { result } = renderHook(() =>
      useTypewriterPlaceholder({
        phrases: ['abc'],
        staticPlaceholder: 'static',
      }),
    )

    expect(result.current.isReducedMotion).toBe(true)
    expect(result.current.placeholder).toBe('static')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('stops animation when reduce-motion toggles on at runtime', () => {
    const { result } = renderHook(() =>
      useTypewriterPlaceholder({
        phrases: ['abc'],
        typingMs: 10,
        holdMs: 30,
        staticPlaceholder: 'static',
      }),
    )

    act(() => {
      vi.advanceTimersByTime(10)
    })
    expect(result.current.placeholder).toBe('a')

    act(() => {
      matchMediaController.emit(true)
    })

    expect(result.current.isReducedMotion).toBe(true)
    expect(result.current.placeholder).toBe('static')

    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.placeholder).toBe('static')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('clears pending timeout on unmount', () => {
    const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout')

    const { unmount } = renderHook(() =>
      useTypewriterPlaceholder({
        phrases: ['abc'],
        typingMs: 10,
        holdMs: 30,
      }),
    )

    act(() => {
      vi.advanceTimersByTime(10)
    })

    expect(vi.getTimerCount()).toBeGreaterThan(0)

    unmount()

    expect(vi.getTimerCount()).toBe(0)
    expect(clearTimeoutSpy).toHaveBeenCalled()
  })
})
