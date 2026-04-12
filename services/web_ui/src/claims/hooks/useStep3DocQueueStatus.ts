import { useEffect, useMemo, useRef, useState } from 'react'

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'
const DEFAULT_MIN_DELAY_MS = 2500
const DEFAULT_MAX_DELAY_MS = 4500
const MAX_RANDOM_UNIT = 0.999_999_999_999

type LegacyMediaQueryList = MediaQueryList & {
  addListener?: (listener: (event: MediaQueryListEvent) => void) => void
  removeListener?: (listener: (event: MediaQueryListEvent) => void) => void
}

export type Step3DocQueueStatus = 'loading' | 'done'

export type Step3DocQueueRng = () => number

export type UseStep3DocQueueStatusOptions = {
  itemIds: readonly string[]
  runKey: string | number
  enabled?: boolean
  minDelayMs?: number
  maxDelayMs?: number
  rng?: Step3DocQueueRng
}

export type UseStep3DocQueueStatusResult = {
  statusById: Record<string, Step3DocQueueStatus>
  allDone: boolean
  isReducedMotion: boolean
}

function defaultRng(): number {
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const values = new Uint32Array(1)
    crypto.getRandomValues(values)
    return values[0] / (0xffff_ffff + 1)
  }
  return Math.random()
}

function readReducedMotionPreference(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  return window.matchMedia(REDUCED_MOTION_QUERY).matches
}

function normalizeDelay(value: number, fallback: number): number {
  if (!Number.isFinite(value)) {
    return fallback
  }
  return Math.max(0, Math.round(value))
}

function resolveDelayRange(minDelayMs: number, maxDelayMs: number): [number, number] {
  const normalizedMin = normalizeDelay(minDelayMs, DEFAULT_MIN_DELAY_MS)
  const normalizedMax = normalizeDelay(maxDelayMs, DEFAULT_MAX_DELAY_MS)
  return normalizedMin <= normalizedMax
    ? [normalizedMin, normalizedMax]
    : [normalizedMax, normalizedMin]
}

function normalizeRandomUnit(value: number): number {
  if (!Number.isFinite(value)) {
    return 0
  }
  if (value <= 0) {
    return 0
  }
  if (value >= 1) {
    return MAX_RANDOM_UNIT
  }
  return value
}

function randomDelay(
  minDelayMs: number,
  maxDelayMs: number,
  rng: Step3DocQueueRng,
): number {
  if (minDelayMs === maxDelayMs) {
    return minDelayMs
  }
  const randomUnit = normalizeRandomUnit(rng())
  const span = maxDelayMs - minDelayMs + 1
  return minDelayMs + Math.floor(randomUnit * span)
}

function buildStatusMap(
  itemIds: readonly string[],
  status: Step3DocQueueStatus,
): Record<string, Step3DocQueueStatus> {
  return Object.fromEntries(itemIds.map((itemId) => [itemId, status]))
}

export function useStep3DocQueueStatus({
  itemIds,
  runKey,
  enabled = true,
  minDelayMs = DEFAULT_MIN_DELAY_MS,
  maxDelayMs = DEFAULT_MAX_DELAY_MS,
  rng,
}: UseStep3DocQueueStatusOptions): UseStep3DocQueueStatusResult {
  const resolvedRng = rng ?? defaultRng
  const [isReducedMotion, setIsReducedMotion] = useState<boolean>(() =>
    readReducedMotionPreference(),
  )
  const [statusById, setStatusById] = useState<Record<string, Step3DocQueueStatus>>(() =>
    buildStatusMap(itemIds, 'loading'),
  )
  const timerIdsRef = useRef<number[]>([])
  const runIdRef = useRef(0)
  const itemIdsSignature = itemIds.join('|')
  const stableItemIds = useMemo(() => [...itemIds], [itemIdsSignature])

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return
    }

    const mediaQueryList = window.matchMedia(REDUCED_MOTION_QUERY)
    setIsReducedMotion(mediaQueryList.matches)

    const handleChange = (event: MediaQueryListEvent) => {
      setIsReducedMotion(event.matches)
    }

    if (typeof mediaQueryList.addEventListener === 'function') {
      mediaQueryList.addEventListener('change', handleChange)
      return () => {
        mediaQueryList.removeEventListener('change', handleChange)
      }
    }

    const legacyQueryList = mediaQueryList as LegacyMediaQueryList
    legacyQueryList.addListener?.(handleChange)
    return () => {
      legacyQueryList.removeListener?.(handleChange)
    }
  }, [])

  useEffect(() => {
    const currentRunId = runIdRef.current + 1
    runIdRef.current = currentRunId

    timerIdsRef.current.forEach((timerId) => {
      window.clearTimeout(timerId)
    })
    timerIdsRef.current = []

    if (stableItemIds.length === 0) {
      setStatusById({})
      return
    }

    if (!enabled) {
      setStatusById(buildStatusMap(stableItemIds, 'loading'))
      return
    }

    if (isReducedMotion) {
      setStatusById(buildStatusMap(stableItemIds, 'done'))
      return
    }

    const [resolvedMinDelayMs, resolvedMaxDelayMs] = resolveDelayRange(
      minDelayMs,
      maxDelayMs,
    )
    setStatusById(buildStatusMap(stableItemIds, 'loading'))

    stableItemIds.forEach((itemId) => {
      const delayMs = randomDelay(resolvedMinDelayMs, resolvedMaxDelayMs, resolvedRng)
      const timerId = window.setTimeout(() => {
        if (runIdRef.current !== currentRunId) {
          return
        }

        setStatusById((previousState) => {
          if (previousState[itemId] === 'done') {
            return previousState
          }
          return {
            ...previousState,
            [itemId]: 'done',
          }
        })
      }, delayMs)

      timerIdsRef.current.push(timerId)
    })

    return () => {
      if (runIdRef.current !== currentRunId) {
        return
      }
      timerIdsRef.current.forEach((timerId) => {
        window.clearTimeout(timerId)
      })
      timerIdsRef.current = []
    }
  }, [
    enabled,
    isReducedMotion,
    itemIdsSignature,
    maxDelayMs,
    minDelayMs,
    resolvedRng,
    runKey,
    stableItemIds,
  ])

  const allDone = useMemo(
    () => stableItemIds.every((itemId) => statusById[itemId] === 'done'),
    [stableItemIds, statusById],
  )

  return {
    statusById,
    allDone,
    isReducedMotion,
  }
}
