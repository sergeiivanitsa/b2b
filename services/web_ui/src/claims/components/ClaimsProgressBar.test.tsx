import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ClaimsProgressBar } from './ClaimsProgressBar'

describe('ClaimsProgressBar', () => {
  it('renders rounded value and clamps to max', () => {
    render(<ClaimsProgressBar label="Готовность документа:" value={129.3} />)

    expect(screen.getByText('Готовность документа:')).toBeTruthy()
    expect(screen.getByText('100%')).toBeTruthy()
    const progress = screen.getByRole('progressbar')
    expect(progress.getAttribute('aria-valuenow')).toBe('100')
  })
})
