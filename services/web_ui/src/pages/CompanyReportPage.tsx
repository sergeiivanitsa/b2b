import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { createCompanyReport, getCompanyPublicH1, getCompanyReportStatus } from '../companyReport/companyReportApi'
import { CompanyReportContractError } from '../companyReport/companyReportH1Contract'
import {
  beginCompanyHead,
  classifyH1Error,
  cleanupCompanyHead,
  errorCode,
  isCanonicalCompanyPath,
  parseCompanyRoute,
  setCompanyHead,
  setCompanySafeTitle,
  STATUS_POLL_INTERVAL_MS,
  type CompanyRouteKind,
  type H1Operation,
} from '../companyReport/companyReportPresentation'
import type { CompanyPublicH1Response } from '../companyReport/companyReportTypes'
import { CompanyReportContent, type CompanyReportView } from '../components/company-report/CompanyReportContent'
import { ApiHttpError } from '../lib/api'

const PENDING_TITLES = [
  'Проверяем компанию',
  'Собираем сведения о должнике',
  'Анализируем данные',
  'Формируем отчёт',
] as const

type RouteIdentity = {
  token: symbol
  inn: string
  kind: CompanyRouteKind
  pathname: string
}

type RetainedDto = {
  inn: string
  canonicalPath: string
  dto: CompanyPublicH1Response
}

type ActiveRequest = {
  route: RouteIdentity
  controller: AbortController
}

type ActiveTimer = {
  route: RouteIdentity
  id: number
}

type RetryDescriptor = {
  route: RouteIdentity
  operation: H1Operation
  allowAutoCreate: boolean
}

function isPendingError(error: unknown): boolean {
  return (
    error instanceof ApiHttpError &&
    error.status === 409 &&
    errorCode(error) === 'report_pending'
  )
}

function isPlainNotFound(error: unknown): boolean {
  return (
    error instanceof ApiHttpError &&
    error.status === 404 &&
    errorCode(error) === 'company_report_not_found'
  )
}

export function CompanyReportPage() {
  const { companyKey } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const parsed = parseCompanyRoute(companyKey, location.search)
  const inn = 'kind' in parsed ? parsed.inn : null
  const routeKind = 'kind' in parsed ? parsed.kind : null

  const [view, setView] = useState<CompanyReportView>(
    inn && routeKind ? { kind: 'loading_h1' } : { kind: 'invalid_route' },
  )
  const routeRef = useRef<RouteIdentity | null>(null)
  const retainedRef = useRef<RetainedDto | null>(null)
  const workRef = useRef<ActiveRequest | null>(null)
  const pollRef = useRef<ActiveRequest | null>(null)
  const timerRef = useRef<ActiveTimer | null>(null)
  const retryRef = useRef<RetryDescriptor | null>(null)
  const autoCreateKeysRef = useRef(new Set<string>())
  const pendingStageRef = useRef(0)
  const pendingCycleRef = useRef(0)

  const isCurrentRoute = useCallback(
    (route: RouteIdentity) => routeRef.current === route,
    [],
  )

  const abortRouteOperations = useCallback((route?: RouteIdentity) => {
    const work = workRef.current
    if (work && (!route || work.route === route)) {
      work.controller.abort()
      if (workRef.current === work) workRef.current = null
    }
    const poll = pollRef.current
    if (poll && (!route || poll.route === route)) {
      poll.controller.abort()
      if (pollRef.current === poll) pollRef.current = null
    }
    const timer = timerRef.current
    if (timer && (!route || timer.route === route)) {
      window.clearTimeout(timer.id)
      if (timerRef.current === timer) timerRef.current = null
    }
  }, [])

  const startWork = useCallback((route: RouteIdentity): ActiveRequest => {
    workRef.current?.controller.abort()
    const request = { route, controller: new AbortController() }
    workRef.current = request
    return request
  }, [])

  const canCommitWork = useCallback(
    (route: RouteIdentity, request: ActiveRequest): boolean =>
      isCurrentRoute(route) &&
      workRef.current === request &&
      !request.controller.signal.aborted,
    [isCurrentRoute],
  )

  const releaseWork = useCallback((request: ActiveRequest) => {
    if (workRef.current === request) workRef.current = null
  }, [])

  const enterPending = useCallback(
    (route: RouteIdentity, resetStage: boolean) => {
      if (!isCurrentRoute(route)) return
      if (resetStage) pendingStageRef.current = 0
      pendingCycleRef.current += 1
      retryRef.current = null
      setView({
        kind: 'pending',
        title: PENDING_TITLES[pendingStageRef.current],
        cycle: pendingCycleRef.current,
      })
      setCompanySafeTitle('Отчёт формируется')
    },
    [isCurrentRoute],
  )

  const showError = useCallback(
    (
      route: RouteIdentity,
      error: unknown,
      operation: H1Operation,
      allowAutoCreate: boolean,
    ) => {
      if (!isCurrentRoute(route)) return
      retainedRef.current = null
      if (error instanceof CompanyReportContractError) {
        retryRef.current = null
        setView({ kind: 'contract_error' })
        setCompanySafeTitle('Неподдерживаемый формат отчёта')
        return
      }
      const classified = classifyH1Error(error, operation)
      if (classified.kind === 'retryable') {
        retryRef.current = { route, operation, allowAutoCreate }
        setView({ kind: 'retryable_error', message: classified.message })
      } else {
        retryRef.current = null
        setView({ kind: 'terminal_error', message: classified.message })
      }
      setCompanySafeTitle(classified.message)
    },
    [isCurrentRoute],
  )

  const createReport = useCallback(
    async (route: RouteIdentity) => {
      if (!isCurrentRoute(route)) return
      const request = startWork(route)
      retryRef.current = null
      setView({ kind: 'loading_h1' })
      setCompanySafeTitle('Запускаем формирование отчёта')
      try {
        await createCompanyReport(route.inn, request.controller.signal)
        if (!canCommitWork(route, request)) return
        releaseWork(request)
        enterPending(route, true)
      } catch (error) {
        if (!canCommitWork(route, request)) return
        releaseWork(request)
        showError(route, error, 'create', false)
      }
    },
    [canCommitWork, enterPending, isCurrentRoute, releaseWork, showError, startWork],
  )

  const loadH1 = useCallback(
    async (route: RouteIdentity, allowAutoCreate: boolean) => {
      if (!isCurrentRoute(route)) return
      retainedRef.current = null
      const request = startWork(route)
      retryRef.current = null
      setView({ kind: 'loading_h1' })
      setCompanySafeTitle('Загружаем сведения о компании')
      try {
        const dto = await getCompanyPublicH1(
          route.inn,
          request.controller.signal,
        )
        if (!canCommitWork(route, request)) return
        releaseWork(request)
        if (
          dto.identity.inn !== route.inn ||
          !isCanonicalCompanyPath(dto.canonical_path, route.inn)
        ) {
          showError(
            route,
            new CompanyReportContractError(),
            'read',
            false,
          )
          return
        }
        if (route.pathname !== dto.canonical_path) {
          retainedRef.current = {
            inn: route.inn,
            canonicalPath: dto.canonical_path,
            dto,
          }
          navigate(dto.canonical_path, { replace: true })
          return
        }
        setView({ kind: 'content', dto })
        setCompanyHead(dto)
      } catch (error) {
        if (!canCommitWork(route, request)) return
        releaseWork(request)
        if (isPendingError(error)) {
          enterPending(route, true)
          return
        }
        if (
          allowAutoCreate &&
          route.kind === 'plain' &&
          isPlainNotFound(error)
        ) {
          const createKey = `${route.kind}:${route.inn}`
          if (!autoCreateKeysRef.current.has(createKey)) {
            autoCreateKeysRef.current.add(createKey)
            void createReport(route)
          } else {
            enterPending(route, true)
          }
          return
        }
        showError(route, error, 'read', allowAutoCreate)
      }
    },
    [
      canCommitWork,
      createReport,
      enterPending,
      isCurrentRoute,
      navigate,
      releaseWork,
      showError,
      startWork,
    ],
  )

  const pollOnce = useCallback(
    async (route: RouteIdentity) => {
      if (!isCurrentRoute(route)) return
      const currentPoll = pollRef.current
      if (currentPoll) {
        if (currentPoll.route === route) return
        currentPoll.controller.abort()
        if (pollRef.current === currentPoll) pollRef.current = null
      }
      const request = { route, controller: new AbortController() }
      pollRef.current = request
      try {
        const status = await getCompanyReportStatus(
          route.inn,
          request.controller.signal,
        )
        if (
          !isCurrentRoute(route) ||
          pollRef.current !== request ||
          request.controller.signal.aborted
        ) {
          return
        }
        pollRef.current = null
        if (status.status === 'pending') {
          pendingStageRef.current = Math.min(
            pendingStageRef.current + 1,
            PENDING_TITLES.length - 1,
          )
          enterPending(route, false)
          return
        }
        await loadH1(route, false)
      } catch (error) {
        if (
          !isCurrentRoute(route) ||
          pollRef.current !== request ||
          request.controller.signal.aborted
        ) {
          return
        }
        pollRef.current = null
        showError(route, error, 'status', false)
      }
    },
    [enterPending, isCurrentRoute, loadH1, showError],
  )

  const retry = useCallback(() => {
    const descriptor = retryRef.current
    if (!descriptor || !isCurrentRoute(descriptor.route)) return
    retryRef.current = null
    if (descriptor.operation === 'read') {
      void loadH1(descriptor.route, descriptor.allowAutoCreate)
      return
    }
    if (descriptor.operation === 'create') {
      void createReport(descriptor.route)
      return
    }
    enterPending(descriptor.route, false)
    void pollOnce(descriptor.route)
  }, [createReport, enterPending, isCurrentRoute, loadH1, pollOnce])

  useEffect(() => {
    abortRouteOperations()
    beginCompanyHead()
    retryRef.current = null
    pendingStageRef.current = 0

    if (!inn || !routeKind) {
      routeRef.current = null
      retainedRef.current = null
      setCompanySafeTitle('Некорректный адрес страницы компании.')
      return
    }

    const route: RouteIdentity = {
      token: Symbol(`${routeKind}:${inn}:${location.pathname}`),
      inn,
      kind: routeKind,
      pathname: location.pathname,
    }
    routeRef.current = route

    const retained = retainedRef.current
    if (
      retained &&
      retained.inn === route.inn &&
      retained.canonicalPath === route.pathname
    ) {
      retainedRef.current = null
      setView({ kind: 'content', dto: retained.dto })
      setCompanyHead(retained.dto)
    } else {
      retainedRef.current = null
      void loadH1(route, route.kind === 'plain')
    }

    return () => {
      if (routeRef.current === route) routeRef.current = null
      abortRouteOperations(route)
      if (retryRef.current?.route === route) retryRef.current = null
    }
  }, [
    abortRouteOperations,
    inn,
    loadH1,
    location.pathname,
    routeKind,
  ])

  const pendingCycle = view.kind === 'pending' ? view.cycle : -1
  useEffect(() => {
    if (view.kind !== 'pending') return
    const route = routeRef.current
    if (!route) return
    const timer: ActiveTimer = {
      route,
      id: window.setTimeout(() => {
        if (timerRef.current === timer) timerRef.current = null
        void pollOnce(route)
      }, STATUS_POLL_INTERVAL_MS),
    }
    timerRef.current = timer
    return () => {
      if (timerRef.current === timer) {
        window.clearTimeout(timer.id)
        timerRef.current = null
      }
    }
  }, [pendingCycle, pollOnce, view.kind])

  useEffect(
    () => () => {
      retainedRef.current = null
      routeRef.current = null
      abortRouteOperations()
      cleanupCompanyHead()
    },
    [abortRouteOperations],
  )

  const displayedView: CompanyReportView =
    inn && routeKind ? view : { kind: 'invalid_route' }
  return <CompanyReportContent view={displayedView} onRetry={retry} />
}
