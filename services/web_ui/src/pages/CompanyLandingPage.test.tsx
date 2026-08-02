import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { CompanyLandingPage } from './CompanyLandingPage'

function LocationProbe() { return <p>{useLocation().pathname}</p> }

describe('CompanyLandingPage', () => {
  it('shares one INN value and navigates only once to the plain resolver', () => {
    render(<MemoryRouter initialEntries={['/']}><Routes><Route path="/" element={<CompanyLandingPage />} /><Route path="/company/:key" element={<LocationProbe />} /></Routes></MemoryRouter>)
    const inputs = screen.getAllByLabelText('ИНН компании') as HTMLInputElement[]
    fireEvent.change(inputs[0], { target: { value: '7700 000 000' } })
    expect(inputs[1].value).toBe('7700000000')
    fireEvent.submit(inputs[1].closest('form')!)
    expect(screen.getByText('/company/7700000000')).toBeTruthy()
  })
})
