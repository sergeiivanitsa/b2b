import { useEffect, useMemo, useRef, useState } from 'react'

const DEFAULT_TYPING_MS = 333
const DEFAULT_HOLD_MS = 1300
const DEFAULT_STATIC_PLACEHOLDER = 'Отправьте сообщение...'
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

type AnimationPhase = 'typing' | 'holding'

type AnimationState = {
  phraseIndex: number
  visibleLength: number
  phase: AnimationPhase
}

type LegacyMediaQueryList = MediaQueryList & {
  addListener?: (listener: (event: MediaQueryListEvent) => void) => void
  removeListener?: (listener: (event: MediaQueryListEvent) => void) => void
}

const INITIAL_STATE: AnimationState = {
  phraseIndex: 0,
  visibleLength: 0,
  phase: 'typing',
}

export type UseTypewriterPlaceholderOptions = {
  phrases: readonly string[]
  typingMs?: number
  holdMs?: number
  loop?: boolean
  paused?: boolean
  enabled?: boolean
  staticPlaceholder?: string
}

export type UseTypewriterPlaceholderResult = {
  placeholder: string
  isReducedMotion: boolean
}

function readReducedMotionPreference(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  return window.matchMedia(REDUCED_MOTION_QUERY).matches
}

function resolveStaticPlaceholder(
  phrases: readonly string[],
  staticPlaceholder: string | undefined,
): string {
  if (staticPlaceholder && staticPlaceholder.trim().length > 0) {
    return staticPlaceholder
  }
  const firstPhrase = phrases[0]
  if (firstPhrase && firstPhrase.trim().length > 0) {
    return firstPhrase
  }
  return DEFAULT_STATIC_PLACEHOLDER
}

export function useTypewriterPlaceholder({
  phrases,
  typingMs = DEFAULT_TYPING_MS,
  holdMs = DEFAULT_HOLD_MS,
  loop = true,
  paused = false,
  enabled = true,
  staticPlaceholder,
}: UseTypewriterPlaceholderOptions): UseTypewriterPlaceholderResult {
  const [animationState, setAnimationState] = useState<AnimationState>(INITIAL_STATE)
  const [isReducedMotion, setIsReducedMotion] = useState<boolean>(() =>
    readReducedMotionPreference(),
  )
  const timeoutRef = useRef<number | null>(null)

  const staticValue = useMemo(
    () => resolveStaticPlaceholder(phrases, staticPlaceholder),
    [phrases, staticPlaceholder],
  )

  useEffect(() => {
    setAnimationState((previousState) => {
      if (phrases.length === 0) {
        if (
          previousState.phraseIndex === INITIAL_STATE.phraseIndex &&
          previousState.visibleLength === INITIAL_STATE.visibleLength &&
          previousState.phase === INITIAL_STATE.phase
        ) {
          return previousState
        }
        return INITIAL_STATE
      }

      const boundedPhraseIndex = Math.min(previousState.phraseIndex, phrases.length - 1)
      const phrase = phrases[boundedPhraseIndex] ?? ''
      const boundedVisibleLength = Math.min(previousState.visibleLength, phrase.length)
      const nextPhase: AnimationPhase =
        boundedVisibleLength < phrase.length ? 'typing' : previousState.phase

      if (
        boundedPhraseIndex === previousState.phraseIndex &&
        boundedVisibleLength === previousState.visibleLength &&
        nextPhase === previousState.phase
      ) {
        return previousState
      }

      return {
        phraseIndex: boundedPhraseIndex,
        visibleLength: boundedVisibleLength,
        phase: nextPhase,
      }
    })
  }, [phrases])

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

  const shouldUseStaticPlaceholder = !enabled || isReducedMotion || phrases.length === 0
  const shouldAnimate = !shouldUseStaticPlaceholder && !paused

  const currentPhrase = phrases[animationState.phraseIndex] ?? ''
  const boundedVisibleLength = Math.min(animationState.visibleLength, currentPhrase.length)
  const animatedPlaceholder = currentPhrase.slice(0, boundedVisibleLength)

  useEffect(() => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }

    if (!shouldAnimate || !currentPhrase) {
      return
    }

    if (animationState.phase === 'typing') {
      if (boundedVisibleLength >= currentPhrase.length) {
        setAnimationState((previousState) =>
          previousState.phase === 'holding'
            ? previousState
            : {
                ...previousState,
                phase: 'holding',
              },
        )
        return
      }

      timeoutRef.current = window.setTimeout(() => {
        setAnimationState((previousState) => {
          const phrase = phrases[previousState.phraseIndex] ?? ''
          if (!phrase) {
            return previousState
          }
          const nextVisibleLength = Math.min(previousState.visibleLength + 1, phrase.length)
          const nextPhase: AnimationPhase =
            nextVisibleLength >= phrase.length ? 'holding' : 'typing'

          if (
            nextVisibleLength === previousState.visibleLength &&
            nextPhase === previousState.phase
          ) {
            return previousState
          }

          return {
            phraseIndex: previousState.phraseIndex,
            visibleLength: nextVisibleLength,
            phase: nextPhase,
          }
        })
      }, typingMs)

      return
    }

    const isLastPhrase = animationState.phraseIndex >= phrases.length - 1
    if (!loop && isLastPhrase) {
      return
    }

    timeoutRef.current = window.setTimeout(() => {
      setAnimationState((previousState) => {
        if (phrases.length === 0) {
          return previousState
        }

        const wasLastPhrase = previousState.phraseIndex >= phrases.length - 1
        const nextPhraseIndex = wasLastPhrase ? 0 : previousState.phraseIndex + 1

        return {
          phraseIndex: nextPhraseIndex,
          visibleLength: 0,
          phase: 'typing',
        }
      })
    }, holdMs)

    return () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current)
        timeoutRef.current = null
      }
    }
  }, [
    animationState.phase,
    animationState.phraseIndex,
    boundedVisibleLength,
    currentPhrase,
    holdMs,
    loop,
    phrases,
    shouldAnimate,
    typingMs,
  ])

  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current)
        timeoutRef.current = null
      }
    }
  }, [])

  return {
    placeholder: shouldUseStaticPlaceholder ? staticValue : animatedPlaceholder,
    isReducedMotion,
  }
}
