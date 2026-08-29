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
  pendingAutoPollDeadlineMs,
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

type PollMode = 'auto' | 'manual'

type PendingTimeline = {
  route: RouteIdentity
  firstObservedAtMs: number
  serverStartedAt: string | null
}

type RetryDescriptor = {
  route: RouteIdentity
  operation: H1Operation
  allowAutoCreate: boolean
  statusMode: PollMode
  resetPendingTimeline: boolean
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
  const pollTimerRef = useRef<ActiveTimer | null>(null)
  const deadlineTimerRef = useRef<ActiveTimer | null>(null)
  const pendingTimelineRef = useRef<PendingTimeline | null>(null)
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
    const pollTimer = pollTimerRef.current
    if (pollTimer && (!route || pollTimer.route === route)) {
      window.clearTimeout(pollTimer.id)
      if (pollTimerRef.current === pollTimer) pollTimerRef.current = null
    }
    const deadlineTimer = deadlineTimerRef.current
    if (deadlineTimer && (!route || deadlineTimer.route === route)) {
      window.clearTimeout(deadlineTimer.id)
      if (deadlineTimerRef.current === deadlineTimer) {
        deadlineTimerRef.current = null
      }
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

  const enterDelayed = useCallback(
    (route: RouteIdentity, checking: boolean) => {
      if (!isCurrentRoute(route)) return
      if (!checking) {
        const poll = pollRef.current
        if (poll?.route === route) {
          poll.controller.abort()
          if (pollRef.current === poll) pollRef.current = null
        }
      }
      const pollTimer = pollTimerRef.current
      if (pollTimer?.route === route) {
        window.clearTimeout(pollTimer.id)
        if (pollTimerRef.current === pollTimer) pollTimerRef.current = null
      }
      const deadlineTimer = deadlineTimerRef.current
      if (deadlineTimer?.route === route) {
        window.clearTimeout(deadlineTimer.id)
        if (deadlineTimerRef.current === deadlineTimer) {
          deadlineTimerRef.current = null
        }
      }
      retryRef.current = checking
        ? null
        : {
            route,
            operation: 'status',
            allowAutoCreate: false,
            statusMode: 'manual',
            resetPendingTimeline: false,
          }
      setView({ kind: 'delayed', checking })
      setCompanySafeTitle('Отчёт ещё формируется')
    },
    [isCurrentRoute],
  )

  const enterPending = useCallback(
    (
      route: RouteIdentity,
      resetStage: boolean,
      serverStartedAt: string | null = null,
    ) => {
      if (!isCurrentRoute(route)) return
      let timeline = pendingTimelineRef.current
      if (resetStage || !timeline || timeline.route !== route) {
        timeline = {
          route,
          firstObservedAtMs: Date.now(),
          serverStartedAt: null,
        }
      }
      if (
        serverStartedAt !== null &&
        Number.isFinite(Date.parse(serverStartedAt))
      ) {
        const knownStartedAtMs = timeline.serverStartedAt
          ? Date.parse(timeline.serverStartedAt)
          : Number.POSITIVE_INFINITY
        if (Date.parse(serverStartedAt) < knownStartedAtMs) {
          timeline = { ...timeline, serverStartedAt }
        }
      }
      pendingTimelineRef.current = timeline
      if (
        pendingAutoPollDeadlineMs(
          timeline.firstObservedAtMs,
          timeline.serverStartedAt,
        ) <= Date.now()
      ) {
        enterDelayed(route, false)
        return
      }
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
    [enterDelayed, isCurrentRoute],
  )

  const showError = useCallback(
    (
      route: RouteIdentity,
      error: unknown,
      operation: H1Operation,
      allowAutoCreate: boolean,
      statusMode: PollMode = 'auto',
      resetPendingTimeline: boolean = true,
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
        retryRef.current = {
          route,
          operation,
          allowAutoCreate,
          statusMode,
          resetPendingTimeline,
        }
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
    async (
      route: RouteIdentity,
      allowAutoCreate: boolean,
      pendingMode: PollMode = 'auto',
      resetPendingTimeline: boolean = true,
    ) => {
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
          if (pendingMode === 'manual') {
            enterDelayed(route, false)
          } else {
            enterPending(route, resetPendingTimeline)
          }
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
        showError(
          route,
          error,
          'read',
          allowAutoCreate,
          pendingMode,
          resetPendingTimeline,
        )
      }
    },
    [
      canCommitWork,
      createReport,
      enterDelayed,
      enterPending,
      isCurrentRoute,
      navigate,
      releaseWork,
      showError,
      startWork,
    ],
  )

  const pollOnce = useCallback(
    async (route: RouteIdentity, mode: PollMode = 'auto') => {
      if (!isCurrentRoute(route)) return
      if (mode === 'manual') enterDelayed(route, true)
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
          if (mode === 'manual') {
            const timeline = pendingTimelineRef.current
            if (timeline?.route === route) {
              const knownStartedAtMs = timeline.serverStartedAt
                ? Date.parse(timeline.serverStartedAt)
                : Number.POSITIVE_INFINITY
              if (
                Number.isFinite(Date.parse(status.started_at)) &&
                Date.parse(status.started_at) < knownStartedAtMs
              ) {
                pendingTimelineRef.current = {
                  ...timeline,
                  serverStartedAt: status.started_at,
                }
              }
            }
            enterDelayed(route, false)
          } else {
            enterPending(route, false, status.started_at)
          }
          return
        }
        await loadH1(route, false, mode, false)
      } catch (error) {
        if (
          !isCurrentRoute(route) ||
          pollRef.current !== request ||
          request.controller.signal.aborted
        ) {
          return
        }
        pollRef.current = null
        showError(route, error, 'status', false, mode)
      }
    },
    [enterDelayed, enterPending, isCurrentRoute, loadH1, showError],
  )

  const retry = useCallback(() => {
    const descriptor = retryRef.current
    if (!descriptor || !isCurrentRoute(descriptor.route)) return
    retryRef.current = null
    if (descriptor.operation === 'read') {
      void loadH1(
        descriptor.route,
        descriptor.allowAutoCreate,
        descriptor.statusMode,
        descriptor.resetPendingTimeline,
      )
      return
    }
    if (descriptor.operation === 'create') {
      void createReport(descriptor.route)
      return
    }
    void pollOnce(descriptor.route, descriptor.statusMode)
  }, [createReport, isCurrentRoute, loadH1, pollOnce])

  useEffect(() => {
    abortRouteOperations()
    beginCompanyHead()
    retryRef.current = null
    pendingStageRef.current = 0
    pendingTimelineRef.current = null

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
      if (pendingTimelineRef.current?.route === route) {
        pendingTimelineRef.current = null
      }
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
    const timeline = pendingTimelineRef.current
    if (!route || !timeline || timeline.route !== route) return
    const remainingMs = Math.max(
      0,
      pendingAutoPollDeadlineMs(
        timeline.firstObservedAtMs,
        timeline.serverStartedAt,
      ) - Date.now(),
    )
    if (remainingMs === 0) {
      enterDelayed(route, false)
      return
    }
    const timer: ActiveTimer = {
      route,
      id: window.setTimeout(() => {
        if (deadlineTimerRef.current === timer) {
          deadlineTimerRef.current = null
        }
        enterDelayed(route, false)
      }, remainingMs),
    }
    deadlineTimerRef.current = timer
    return () => {
      if (deadlineTimerRef.current === timer) {
        window.clearTimeout(timer.id)
        deadlineTimerRef.current = null
      }
    }
  }, [enterDelayed, pendingCycle, view.kind])

  useEffect(() => {
    if (view.kind !== 'pending') return
    const route = routeRef.current
    if (!route) return
    const timer: ActiveTimer = {
      route,
      id: window.setTimeout(() => {
        if (pollTimerRef.current === timer) pollTimerRef.current = null
        void pollOnce(route)
      }, STATUS_POLL_INTERVAL_MS),
    }
    pollTimerRef.current = timer
    return () => {
      if (pollTimerRef.current === timer) {
        window.clearTimeout(timer.id)
        pollTimerRef.current = null
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
