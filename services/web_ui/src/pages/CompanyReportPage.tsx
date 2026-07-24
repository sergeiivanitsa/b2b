import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { CompanyReportContent } from '../components/company-report/CompanyReportContent'
import { createCompanyReport, getCompanyReport, getCompanyReportStatus } from '../companyReport/companyReportApi'
import type { CompanyReportResponse } from '../companyReport/companyReportTypes'
import { errorCode, parseCompanyKey, safeErrorMessage, STATUS_POLL_INTERVAL_MS } from '../companyReport/companyReportPresentation'
import { ApiHttpError } from '../lib/api'

type ViewState = 'loading' | 'report' | 'not_found' | 'pending' | 'error'
type RetryOperation = 'get' | 'create' | 'status'
type ErrorKind = 'generic' | 'unauthenticated' | 'forbidden'
type ViewError = { message: string; kind: ErrorKind; retryOperation: RetryOperation | null }

function toViewError(error: unknown, retryOperation: RetryOperation): ViewError {
  if (error instanceof ApiHttpError && error.status === 401) {
    return { message: safeErrorMessage(error), kind: 'unauthenticated', retryOperation: null }
  }
  if (error instanceof ApiHttpError && error.status === 403) {
    return { message: safeErrorMessage(error), kind: 'forbidden', retryOperation: null }
  }
  return { message: safeErrorMessage(error), kind: 'generic', retryOperation }
}

export function CompanyReportPage() {
  const { companyKey } = useParams()
  const parsed = parseCompanyKey(companyKey)
  const inn = 'inn' in parsed ? parsed.inn : null
  const [view, setView] = useState<ViewState>('loading')
  const [report, setReport] = useState<CompanyReportResponse | undefined>()
  const [viewError, setViewError] = useState<ViewError | null>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)
  const requestRef = useRef<AbortController | null>(null)
  const aiRequestRef = useRef<AbortController | null>(null)

  const cancelWork = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    requestRef.current?.abort()
    requestRef.current = null
  }, [])
  const startRequest = useCallback(() => {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    return controller
  }, [])

  const loadReport = useCallback(async (targetInn: string) => {
    const controller = startRequest()
    setView('loading')
    setViewError(null)
    try {
      const next = await getCompanyReport(targetInn, { signal: controller.signal })
      if (controller.signal.aborted) return
      setReport(next)
      setView('report')
    } catch (error) {
      if (controller.signal.aborted) return
      if (error instanceof ApiHttpError && error.status === 404) {
        setView('not_found')
        return
      }
      if (error instanceof ApiHttpError && error.status === 409 && errorCode(error) === 'report_pending') {
        setView('pending')
        return
      }
      setViewError(toViewError(error, 'get'))
      setView('error')
    }
  }, [startRequest])

  const poll = useCallback((targetInn: string) => {
    const run = async () => {
      const controller = startRequest()
      try {
        const status = await getCompanyReportStatus(targetInn, controller.signal)
        if (controller.signal.aborted) return
        if (status.status === 'pending') {
          timerRef.current = window.setTimeout(run, STATUS_POLL_INTERVAL_MS)
          return
        }
        await loadReport(targetInn)
      } catch (error) {
        if (controller.signal.aborted) return
        setViewError(toViewError(error, 'status'))
        setView('error')
      }
    }
    timerRef.current = window.setTimeout(run, STATUS_POLL_INTERVAL_MS)
  }, [loadReport, startRequest])

  const create = useCallback(async () => {
    if (!inn) return
    cancelWork()
    setView('loading')
    setViewError(null)
    const controller = startRequest()
    try {
      await createCompanyReport(inn, controller.signal)
      if (!controller.signal.aborted) setView('pending')
    } catch (error) {
      if (controller.signal.aborted) return
      setViewError(toViewError(error, 'create'))
      setView('error')
    }
  }, [cancelWork, inn, startRequest])

  useEffect(() => {
    cancelWork()
    aiRequestRef.current?.abort()
    setReport(undefined)
    setAiError(null)
    setAiLoading(false)
    if (!inn) {
      setView('error')
      setViewError({ message: 'Некорректный адрес страницы компании.', kind: 'generic', retryOperation: null })
      return cancelWork
    }
    void loadReport(inn)
    return () => {
      cancelWork()
      aiRequestRef.current?.abort()
    }
  }, [cancelWork, inn, loadReport])

  useEffect(() => {
    if (view === 'pending' && inn) poll(inn)
    return () => {
      if (view === 'pending') cancelWork()
    }
  }, [cancelWork, inn, poll, view])

  const retry = useCallback(() => {
    if (!inn || !viewError?.retryOperation) return
    cancelWork()
    if (viewError.retryOperation === 'get') void loadReport(inn)
    if (viewError.retryOperation === 'create') void create()
    if (viewError.retryOperation === 'status') {
      setViewError(null)
      setView('pending')
    }
  }, [cancelWork, create, inn, loadReport, viewError])

  const loadAi = useCallback(async () => {
    if (!inn || !report || aiLoading) return
    aiRequestRef.current?.abort()
    const controller = new AbortController()
    aiRequestRef.current = controller
    setAiLoading(true)
    setAiError(null)
    try {
      const response = await getCompanyReport(inn, { includeAiExplanation: true, signal: controller.signal })
      if (!controller.signal.aborted) {
        setReport((current) => current ? { ...current, ai_explanation: response.ai_explanation } : current)
      }
    } catch (error) {
      if (!controller.signal.aborted) setAiError(safeErrorMessage(error))
    } finally {
      if (!controller.signal.aborted) setAiLoading(false)
    }
  }, [aiLoading, inn, report])

  if (!inn) {
    return <CompanyReportContent inn="" error={viewError} />
  }
  return <CompanyReportContent inn={inn} response={report} pending={view === 'pending'} notFound={view === 'not_found'} error={view === 'error' ? viewError : null} onCreate={create} onRetry={retry} onLoadAi={view === 'report' ? loadAi : undefined} aiLoading={aiLoading} aiError={aiError} />
}
