import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { CompanyReportContent } from '../components/company-report/CompanyReportContent'
import { createCompanyReport, getCompanyReport, getCompanyReportStatus } from '../companyReport/companyReportApi'
import type { CompanyReportResponse } from '../companyReport/companyReportTypes'
import { errorCode, isCanonicalCompanyPath, parseCompanyKey, safeErrorMessage, STATUS_POLL_INTERVAL_MS } from '../companyReport/companyReportPresentation'
import { ApiHttpError } from '../lib/api'

type ViewState = 'loading' | 'report' | 'pending' | 'error'
type RetryOperation = 'get' | 'create' | 'status'
type ErrorKind = 'generic' | 'unauthenticated' | 'forbidden'
type ViewError = { message: string; kind: ErrorKind; retryOperation: RetryOperation | null }

function toViewError(error: unknown, retryOperation: RetryOperation): ViewError {
  if (error instanceof ApiHttpError && error.status === 401) return { message: safeErrorMessage(error), kind: 'unauthenticated', retryOperation: null }
  if (error instanceof ApiHttpError && error.status === 403) return { message: safeErrorMessage(error), kind: 'forbidden', retryOperation: null }
  return { message: safeErrorMessage(error), kind: 'generic', retryOperation }
}

export function CompanyReportPage() {
  const { companyKey } = useParams()
  const parsed = parseCompanyKey(companyKey)
  const inn = 'inn' in parsed ? parsed.inn : null
  const routeKind = 'kind' in parsed ? parsed.kind : null
  const location = useLocation()
  const navigate = useNavigate()
  const [view, setView] = useState<ViewState>('loading')
  const [report, setReport] = useState<CompanyReportResponse | undefined>()
  const [viewError, setViewError] = useState<ViewError | null>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)
  const requestRef = useRef<AbortController | null>(null)
  const aiRequestRef = useRef<AbortController | null>(null)
  const autoStartRef = useRef<string | null>(null)

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

  const create = useCallback(async (targetInn: string) => {
    cancelWork()
    setView('loading')
    setViewError(null)
    const controller = startRequest()
    try {
      await createCompanyReport(targetInn, controller.signal)
      if (!controller.signal.aborted) setView('pending')
    } catch (error) {
      if (controller.signal.aborted) return
      setViewError(toViewError(error, 'create'))
      setView('error')
    }
  }, [cancelWork, startRequest])

  const loadReport = useCallback(async (targetInn: string, targetKind: 'plain' | 'canonical') => {
    const controller = startRequest()
    setView('loading')
    setViewError(null)
    try {
      const next = await getCompanyReport(targetInn, { signal: controller.signal })
      if (controller.signal.aborted) return
      const canonicalPath = next.canonical_path
      if (targetKind === 'plain' && typeof canonicalPath === 'string' && isCanonicalCompanyPath(canonicalPath, targetInn) && canonicalPath !== location.pathname) {
        navigate(canonicalPath, { replace: true })
        return
      }
      setReport(next)
      setView('report')
    } catch (error) {
      if (controller.signal.aborted) return
      if (error instanceof ApiHttpError && error.status === 409 && errorCode(error) === 'report_pending') {
        setView('pending')
        return
      }
      if (targetKind === 'plain' && error instanceof ApiHttpError && error.status === 404 && errorCode(error) === 'company_report_not_found') {
        const key = `plain:${targetInn}`
        if (autoStartRef.current !== key) {
          autoStartRef.current = key
          void create(targetInn)
        }
        return
      }
      setViewError(toViewError(error, 'get'))
      setView('error')
    }
  }, [create, location.pathname, navigate, startRequest])

  const poll = useCallback((targetInn: string, targetKind: 'plain' | 'canonical') => {
    const run = async () => {
      const controller = startRequest()
      try {
        const status = await getCompanyReportStatus(targetInn, controller.signal)
        if (controller.signal.aborted) return
        if (status.status === 'pending') {
          timerRef.current = window.setTimeout(run, STATUS_POLL_INTERVAL_MS)
          return
        }
        await loadReport(targetInn, targetKind)
      } catch (error) {
        if (controller.signal.aborted) return
        setViewError(toViewError(error, 'status'))
        setView('error')
      }
    }
    timerRef.current = window.setTimeout(run, STATUS_POLL_INTERVAL_MS)
  }, [loadReport, startRequest])

  useEffect(() => {
    cancelWork()
    aiRequestRef.current?.abort()
    setReport(undefined)
    setAiError(null)
    setAiLoading(false)
    autoStartRef.current = null
    if (!inn || !routeKind) {
      setView('error')
      setViewError({ message: 'Некорректный адрес страницы компании.', kind: 'generic', retryOperation: null })
      return cancelWork
    }
    void loadReport(inn, routeKind)
    return () => {
      cancelWork()
      aiRequestRef.current?.abort()
    }
  }, [cancelWork, inn, loadReport, routeKind])

  useEffect(() => {
    if (view === 'pending' && inn && routeKind) poll(inn, routeKind)
    return () => {
      if (view === 'pending') cancelWork()
    }
  }, [cancelWork, inn, poll, routeKind, view])

  const retry = useCallback(() => {
    if (!inn || !routeKind || !viewError?.retryOperation) return
    cancelWork()
    if (viewError.retryOperation === 'get') void loadReport(inn, routeKind)
    if (viewError.retryOperation === 'create') void create(inn)
    if (viewError.retryOperation === 'status') {
      setViewError(null)
      setView('pending')
    }
  }, [cancelWork, create, inn, loadReport, routeKind, viewError])

  const loadAi = useCallback(async () => {
    if (!inn || !report || aiLoading) return
    aiRequestRef.current?.abort()
    const controller = new AbortController()
    aiRequestRef.current = controller
    setAiLoading(true)
    setAiError(null)
    try {
      const response = await getCompanyReport(inn, { includeAiExplanation: true, signal: controller.signal })
      if (!controller.signal.aborted) setReport((current) => current ? { ...current, ai_explanation: response.ai_explanation } : current)
    } catch (error) {
      if (!controller.signal.aborted) setAiError(safeErrorMessage(error))
    } finally {
      if (!controller.signal.aborted) setAiLoading(false)
    }
  }, [aiLoading, inn, report])

  if (!inn) return <CompanyReportContent inn="" error={viewError} />
  return <CompanyReportContent inn={inn} response={report} pending={view === 'pending'} error={view === 'error' ? viewError : null} onCreate={() => void create(inn)} onRetry={retry} onLoadAi={view === 'report' ? loadAi : undefined} aiLoading={aiLoading} aiError={aiError} />
}
