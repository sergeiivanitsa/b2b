import { useEffect, useMemo, useState } from 'react'

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

type KeyedAnimationState = {
  phrasesIdentity: PhrasesIdentity
  animation: AnimationState
}

type PhrasesIdentity = {
  key: string
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
  const phrasesKey = JSON.stringify(phrases)
  const stablePhrases = useMemo<readonly string[]>(
    () => JSON.parse(phrasesKey) as string[],
    [phrasesKey],
  )
  const phrasesIdentity = useMemo<PhrasesIdentity>(
    () => ({ key: phrasesKey }),
    [phrasesKey],
  )
  const [keyedAnimationState, setKeyedAnimationState] = useState<KeyedAnimationState>(
    () => ({ phrasesIdentity, animation: INITIAL_STATE }),
  )
  const [isReducedMotion, setIsReducedMotion] = useState<boolean>(() =>
    readReducedMotionPreference(),
  )
  const animationState =
    keyedAnimationState.phrasesIdentity === phrasesIdentity
      ? keyedAnimationState.animation
      : INITIAL_STATE

  const staticValue = useMemo(
    () => resolveStaticPlaceholder(stablePhrases, staticPlaceholder),
    [stablePhrases, staticPlaceholder],
  )

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

  const shouldUseStaticPlaceholder =
    !enabled || isReducedMotion || stablePhrases.length === 0
  const shouldAnimate = !shouldUseStaticPlaceholder && !paused

  const currentPhrase = stablePhrases[animationState.phraseIndex] ?? ''
  const boundedVisibleLength = Math.min(animationState.visibleLength, currentPhrase.length)
  const animatedPlaceholder = currentPhrase.slice(0, boundedVisibleLength)

  useEffect(() => {
    if (!shouldAnimate || !currentPhrase) {
      return
    }

    let timeoutId: number
    if (animationState.phase === 'typing') {
      timeoutId = window.setTimeout(() => {
        setKeyedAnimationState((previousState) => {
          const previousAnimation =
            previousState.phrasesIdentity === phrasesIdentity
              ? previousState.animation
              : INITIAL_STATE
          const phrase = stablePhrases[previousAnimation.phraseIndex] ?? ''
          if (!phrase) {
            return previousState
          }
          const nextVisibleLength = Math.min(
            previousAnimation.visibleLength + 1,
            phrase.length,
          )
          const nextPhase: AnimationPhase =
            nextVisibleLength >= phrase.length ? 'holding' : 'typing'

          if (
            previousState.phrasesIdentity === phrasesIdentity &&
            nextVisibleLength === previousAnimation.visibleLength &&
            nextPhase === previousAnimation.phase
          ) {
            return previousState
          }

          return {
            phrasesIdentity,
            animation: {
              phraseIndex: previousAnimation.phraseIndex,
              visibleLength: nextVisibleLength,
              phase: nextPhase,
            },
          }
        })
      }, typingMs)
    } else {
      const isLastPhrase = animationState.phraseIndex >= stablePhrases.length - 1
      if (!loop && isLastPhrase) {
        return
      }

      timeoutId = window.setTimeout(() => {
        setKeyedAnimationState((previousState) => {
          const previousAnimation =
            previousState.phrasesIdentity === phrasesIdentity
              ? previousState.animation
              : INITIAL_STATE
          if (stablePhrases.length === 0) {
            return previousState
          }

          const wasLastPhrase =
            previousAnimation.phraseIndex >= stablePhrases.length - 1
          const nextPhraseIndex = wasLastPhrase
            ? 0
            : previousAnimation.phraseIndex + 1

          return {
            phrasesIdentity,
            animation: {
              phraseIndex: nextPhraseIndex,
              visibleLength: 0,
              phase: 'typing',
            },
          }
        })
      }, holdMs)
    }

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [
    animationState.phase,
    animationState.phraseIndex,
    boundedVisibleLength,
    currentPhrase,
    holdMs,
    loop,
    phrasesIdentity,
    shouldAnimate,
    stablePhrases,
    typingMs,
  ])

  return {
    placeholder: shouldUseStaticPlaceholder ? staticValue : animatedPlaceholder,
    isReducedMotion,
  }
}
