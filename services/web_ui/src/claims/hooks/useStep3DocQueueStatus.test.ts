import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useStep3DocQueueStatus } from './useStep3DocQueueStatus'

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

type MatchMediaListener = (event: MediaQueryListEvent) => void

type MatchMediaController = {
  emit: (nextMatches: boolean) => void
}

const STEP3_ITEM_IDS = [
  'pdf_claim',
  'docx_claim',
  'cover_letter',
  'penalty_table',
  'instructions',
] as const

const initialMatchMedia = window.matchMedia

function createSequenceRng(values: readonly number[]): () => number {
  let index = 0
  return () => {
    const value =
      index < values.length ? values[index] : values[values.length - 1]
    index += 1
    return value ?? 0
  }
}

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

describe('useStep3DocQueueStatus', () => {
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

  it('starts with loading statuses and completes items independently with deterministic rng', () => {
    const rng = vi.fn(createSequenceRng([0, 0.25, 0.5, 0.75, 0.999999]))

    const { result } = renderHook(() =>
      useStep3DocQueueStatus({
        itemIds: STEP3_ITEM_IDS,
        runKey: 'claim-1',
        minDelayMs: 2500,
        maxDelayMs: 4500,
        rng,
      }),
    )

    expect(result.current.allDone).toBe(false)
    expect(result.current.statusById).toEqual({
      pdf_claim: 'loading',
      docx_claim: 'loading',
      cover_letter: 'loading',
      penalty_table: 'loading',
      instructions: 'loading',
    })
    expect(rng).toHaveBeenCalledTimes(5)

    act(() => {
      vi.advanceTimersByTime(2500)
    })
    expect(result.current.statusById.pdf_claim).toBe('done')
    expect(result.current.statusById.docx_claim).toBe('loading')

    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(result.current.statusById.docx_claim).toBe('done')

    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(result.current.statusById.cover_letter).toBe('done')

    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(result.current.statusById.penalty_table).toBe('done')
    expect(result.current.allDone).toBe(false)

    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(result.current.statusById.instructions).toBe('done')
    expect(result.current.allDone).toBe(true)
  })

  it('does not reset statuses on rerender with the same runKey', () => {
    const rng = vi.fn(createSequenceRng([0, 1, 1, 1, 1]))
    const { result, rerender } = renderHook(
      ({ runKey, itemIds }: { runKey: string; itemIds: readonly string[] }) =>
        useStep3DocQueueStatus({
          itemIds,
          runKey,
          minDelayMs: 100,
          maxDelayMs: 300,
          rng,
        }),
      {
        initialProps: {
          runKey: 'claim-1',
          itemIds: STEP3_ITEM_IDS,
        },
      },
    )

    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.statusById.pdf_claim).toBe('done')
    expect(result.current.statusById.docx_claim).toBe('loading')

    rerender({
      runKey: 'claim-1',
      itemIds: [...STEP3_ITEM_IDS],
    })

    expect(result.current.statusById.pdf_claim).toBe('done')
    expect(result.current.statusById.docx_claim).toBe('loading')
    expect(rng).toHaveBeenCalledTimes(5)

    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(result.current.allDone).toBe(true)
  })

  it('restarts the queue when runKey changes', () => {
    const rng = vi.fn(createSequenceRng([1, 1, 1, 1, 1, 0, 0, 0, 0, 0]))
    const { result, rerender } = renderHook(
      ({ runKey }: { runKey: string }) =>
        useStep3DocQueueStatus({
          itemIds: STEP3_ITEM_IDS,
          runKey,
          minDelayMs: 100,
          maxDelayMs: 300,
          rng,
        }),
      {
        initialProps: {
          runKey: 'claim-1',
        },
      },
    )

    expect(vi.getTimerCount()).toBe(5)

    act(() => {
      vi.advanceTimersByTime(150)
    })
    expect(result.current.allDone).toBe(false)

    rerender({ runKey: 'claim-2' })
    expect(vi.getTimerCount()).toBe(5)
    expect(result.current.statusById).toEqual({
      pdf_claim: 'loading',
      docx_claim: 'loading',
      cover_letter: 'loading',
      penalty_table: 'loading',
      instructions: 'loading',
    })

    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.allDone).toBe(true)
    expect(rng).toHaveBeenCalledTimes(10)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('completes immediately in reduced-motion mode without timers', () => {
    matchMediaController.emit(true)
    const rng = vi.fn(createSequenceRng([0.1, 0.2, 0.3, 0.4, 0.5]))

    const { result } = renderHook(() =>
      useStep3DocQueueStatus({
        itemIds: STEP3_ITEM_IDS,
        runKey: 'claim-1',
        rng,
      }),
    )

    expect(result.current.isReducedMotion).toBe(true)
    expect(result.current.allDone).toBe(true)
    expect(result.current.statusById).toEqual({
      pdf_claim: 'done',
      docx_claim: 'done',
      cover_letter: 'done',
      penalty_table: 'done',
      instructions: 'done',
    })
    expect(vi.getTimerCount()).toBe(0)
    expect(rng).toHaveBeenCalledTimes(0)
  })

  it('does not start timers while queue is disabled', () => {
    const rng = vi.fn(createSequenceRng([0.1, 0.2, 0.3, 0.4, 0.5]))

    const { result } = renderHook(() =>
      useStep3DocQueueStatus({
        itemIds: STEP3_ITEM_IDS,
        runKey: 'claim-1',
        enabled: false,
        rng,
      }),
    )

    expect(result.current.allDone).toBe(false)
    expect(result.current.statusById).toEqual({
      pdf_claim: 'loading',
      docx_claim: 'loading',
      cover_letter: 'loading',
      penalty_table: 'loading',
      instructions: 'loading',
    })
    expect(vi.getTimerCount()).toBe(0)
    expect(rng).toHaveBeenCalledTimes(0)
  })

})
