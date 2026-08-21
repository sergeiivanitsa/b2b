import { useEffect, useMemo, useState } from 'react'

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

type QueueState = {
  identity: QueueIdentity
  statusById: Record<string, Step3DocQueueStatus>
}

type QueueIdentity = {
  key: string
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
  const itemIdsKey = JSON.stringify(itemIds)
  const stableItemIds = useMemo<readonly string[]>(
    () => JSON.parse(itemIdsKey) as string[],
    [itemIdsKey],
  )
  const [resolvedMinDelayMs, resolvedMaxDelayMs] = resolveDelayRange(
    minDelayMs,
    maxDelayMs,
  )
  const queueKey = JSON.stringify([
    runKey,
    itemIdsKey,
    enabled,
    isReducedMotion,
    resolvedMinDelayMs,
    resolvedMaxDelayMs,
  ])
  const queueIdentity = useMemo<QueueIdentity>(() => ({ key: queueKey }), [queueKey])
  const initialStatus = isReducedMotion ? 'done' : 'loading'
  const baselineStatusById = buildStatusMap(stableItemIds, initialStatus)
  const [queueState, setQueueState] = useState<QueueState>(() => ({
    identity: queueIdentity,
    statusById: baselineStatusById,
  }))
  const statusById =
    queueState.identity === queueIdentity ? queueState.statusById : baselineStatusById

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return
    }

    const mediaQueryList = window.matchMedia(REDUCED_MOTION_QUERY)

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
    if (stableItemIds.length === 0 || !enabled || isReducedMotion) {
      return
    }

    let cancelled = false
    const timerIds: number[] = []

    stableItemIds.forEach((itemId) => {
      const delayMs = randomDelay(
        resolvedMinDelayMs,
        resolvedMaxDelayMs,
        resolvedRng,
      )
      const timerId = window.setTimeout(() => {
        if (cancelled) {
          return
        }

        setQueueState((previousState) => {
          const previousStatusById =
            previousState.identity === queueIdentity
              ? previousState.statusById
              : buildStatusMap(stableItemIds, 'loading')
          if (previousStatusById[itemId] === 'done') {
            return previousState.identity === queueIdentity
              ? previousState
              : { identity: queueIdentity, statusById: previousStatusById }
          }
          return {
            identity: queueIdentity,
            statusById: {
              ...previousStatusById,
              [itemId]: 'done',
            },
          }
        })
      }, delayMs)

      timerIds.push(timerId)
    })

    return () => {
      cancelled = true
      timerIds.forEach((timerId) => {
        window.clearTimeout(timerId)
      })
    }
  }, [
    enabled,
    isReducedMotion,
    queueIdentity,
    resolvedMaxDelayMs,
    resolvedMinDelayMs,
    resolvedRng,
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
