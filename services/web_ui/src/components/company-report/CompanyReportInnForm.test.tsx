import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CompanyReportInnForm } from './CompanyReportInnForm'

describe('CompanyReportInnForm', () => {
  afterEach(cleanup)
  it('removes whitespace and submits only exact ASCII INN digits', () => {
    const onChange = vi.fn()
    const onSubmit = vi.fn()
    const { rerender } = render(<CompanyReportInnForm id="inn" value="" onChange={onChange} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByLabelText('ИНН компании'), { target: { value: '7700 000 000' } })
    expect(onChange).toHaveBeenCalledWith('7700000000')
    rerender(<CompanyReportInnForm id="inn" value="7700000000" onChange={onChange} onSubmit={onSubmit} />)
    fireEvent.submit(screen.getByRole('button', { name: 'Проверить' }).closest('form')!)
    expect(onSubmit).toHaveBeenCalledWith('7700000000')
  })

  it('shows a live validation error and does not submit invalid input', () => {
    const onSubmit = vi.fn()
    render(<CompanyReportInnForm id="inn" value="770000000x" onChange={vi.fn()} onSubmit={onSubmit} />)
    fireEvent.click(screen.getByRole('button', { name: 'Проверить' }))
    expect(screen.getByText('Введите ИНН из 10 или 12 цифр.')).toBeTruthy()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('keeps validation and submit behavior when its presentation text changes', () => {
    const onSubmit = vi.fn()
    render(<CompanyReportInnForm id="inn" value="7700000000" onChange={vi.fn()} onSubmit={onSubmit} compact placeholder="ИНН" submitLabel="Проверить должника" />)

    expect(screen.getByPlaceholderText('ИНН')).toBeTruthy()
    fireEvent.submit(screen.getByRole('button', { name: 'Проверить должника' }).closest('form')!)
    expect(onSubmit).toHaveBeenCalledWith('7700000000')
  })
})
