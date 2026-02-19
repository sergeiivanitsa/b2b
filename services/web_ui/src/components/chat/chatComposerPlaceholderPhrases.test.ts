import { describe, expect, it } from 'vitest'

import {
  CHAT_COMPOSER_PLACEHOLDER_PHRASES,
  CHAT_COMPOSER_STATIC_PLACEHOLDER,
} from './chatComposerPlaceholderPhrases'

describe('chatComposerPlaceholderPhrases', () => {
  it('contains non-empty placeholder phrases', () => {
    expect(CHAT_COMPOSER_PLACEHOLDER_PHRASES.length).toBeGreaterThan(0)
    expect(CHAT_COMPOSER_PLACEHOLDER_PHRASES.every((phrase) => phrase.trim().length > 0)).toBe(
      true,
    )
  })

  it('contains the expected number of phrases', () => {
    expect(CHAT_COMPOSER_PLACEHOLDER_PHRASES.length).toBe(19)
  })

  it('uses the first phrase as static placeholder fallback', () => {
    expect(CHAT_COMPOSER_STATIC_PLACEHOLDER.trim().length).toBeGreaterThan(0)
    expect(CHAT_COMPOSER_STATIC_PLACEHOLDER).toBe(CHAT_COMPOSER_PLACEHOLDER_PHRASES[0])
  })
})
