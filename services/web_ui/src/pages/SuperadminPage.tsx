import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import {
  ORG_STATUSES,
  addCredits,
  createCompany,
  getCompany,
  inviteCompanyAdmin,
  listOrgs,
  updateOrgStatus,
} from '../superadmin/orgsApi'
import type {
  AddCreditsInput,
  GetCompanyResponse,
  OrgStatus,
  SuperadminOrg,
} from '../superadmin/orgsApi'
import {
  SUPERADMIN_TEXT,
  formatCreditsSuccessMessage,
  formatSuperadminError,
  isCreditsDuplicateIdempotencyConflict,
} from '../superadmin/superadminUx'

type StatusFilter = 'all' | OrgStatus
type OrgStatusDraftMap = Record<number, OrgStatus>
type OrgSavingMap = Record<number, boolean>
type OrgErrorMap = Record<number, string | null>
type CopyFeedback = { kind: 'success' | 'error'; text: string }
type OperationFeedback = { kind: 'success' | 'error'; text: string }
type CreditRequestPayload = AddCreditsInput & { companyId: number }

function formatCreatedAt(value: string | null): string {
  if (!value) {
    return '-'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

function normalizeDigits(value: string): string {
  return value.replace(/\D/g, '')
}

function normalizeEmail(value: string): string {
  return value.trim().toLowerCase()
}

function isValidBasicEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}

function parsePositiveInteger(value: string): number | null {
  if (!/^\d+$/.test(value)) {
    return null
  }
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return null
  }
  return parsed
}

function generateIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `credit-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function buildDraftStatusMap(orgs: SuperadminOrg[]): OrgStatusDraftMap {
  const result: OrgStatusDraftMap = {}
  for (const org of orgs) {
    result[org.id] = org.status
  }
  return result
}

function feedbackClassName(kind: 'success' | 'error'): string {
  return kind === 'success' ? 'message message--success' : 'message message--error'
}

async function copyTextWithFallback(value: string): Promise<boolean> {
  if (
    typeof navigator !== 'undefined' &&
    navigator.clipboard &&
    typeof navigator.clipboard.writeText === 'function'
  ) {
    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch {
      // Continue with fallback.
    }
  }

  if (
    typeof document === 'undefined' ||
    typeof document.execCommand !== 'function' ||
    !document.body
  ) {
    return false
  }

  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'absolute'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  let copied = false
  try {
    copied = document.execCommand('copy')
  } catch {
    copied = false
  }
  document.body.removeChild(textarea)
  return copied
}

export function SuperadminPage() {
  const { user } = useAuth()
  const [orgs, setOrgs] = useState<SuperadminOrg[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [nameFilter, setNameFilter] = useState('')
  const [innFilter, setInnFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [draftStatusByOrgId, setDraftStatusByOrgId] = useState<OrgStatusDraftMap>({})
  const [isSavingByOrgId, setIsSavingByOrgId] = useState<OrgSavingMap>({})
  const [rowErrorByOrgId, setRowErrorByOrgId] = useState<OrgErrorMap>({})
  const [createName, setCreateName] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [createSuccessMessage, setCreateSuccessMessage] = useState<string | null>(null)
  const [createdOrganizationId, setCreatedOrganizationId] = useState<number | null>(null)
  const [copyFeedback, setCopyFeedback] = useState<CopyFeedback | null>(null)
  const [viewOrganizationId, setViewOrganizationId] = useState('')
  const [isViewLoading, setIsViewLoading] = useState(false)
  const [viewError, setViewError] = useState<string | null>(null)
  const [viewResult, setViewResult] = useState<GetCompanyResponse | null>(null)
  const [hasTriedView, setHasTriedView] = useState(false)
  const [inviteOrganizationId, setInviteOrganizationId] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [isInviting, setIsInviting] = useState(false)
  const [inviteFeedback, setInviteFeedback] = useState<OperationFeedback | null>(null)
  const [inviteToken, setInviteToken] = useState<string | null>(null)
  const [inviteLink, setInviteLink] = useState<string | null>(null)
  const [creditsOrganizationId, setCreditsOrganizationId] = useState('')
  const [creditsAmount, setCreditsAmount] = useState('')
  const [creditsReason, setCreditsReason] = useState('')
  const [isCreditsSubmitting, setIsCreditsSubmitting] = useState(false)
  const [creditsFeedback, setCreditsFeedback] = useState<OperationFeedback | null>(null)
  const [lastSentCreditsPayload, setLastSentCreditsPayload] = useState<CreditRequestPayload | null>(
    null,
  )
  const loadSeqRef = useRef(0)
  const activeLoadControllerRef = useRef<AbortController | null>(null)
  const isMountedRef = useRef(true)

  const loadOrgs = useCallback(async ({ showLoading = true }: { showLoading?: boolean } = {}) => {
    const sequence = loadSeqRef.current + 1
    loadSeqRef.current = sequence

    activeLoadControllerRef.current?.abort()
    const abortController = new AbortController()
    activeLoadControllerRef.current = abortController

    if (showLoading) {
      setIsLoading(true)
      setErrorMessage(null)
    }

    try {
      const response = await listOrgs({ signal: abortController.signal })
      if (
        !isMountedRef.current ||
        abortController.signal.aborted ||
        sequence !== loadSeqRef.current
      ) {
        return
      }
      const sortedOrgs = [...response.orgs].sort((a, b) => a.id - b.id)
      setOrgs(sortedOrgs)
      setDraftStatusByOrgId(buildDraftStatusMap(sortedOrgs))
      setRowErrorByOrgId({})
      if (showLoading) {
        setErrorMessage(null)
      }
    } catch (error) {
      if (
        !isMountedRef.current ||
        abortController.signal.aborted ||
        sequence !== loadSeqRef.current
      ) {
        return
      }
      if (!showLoading) {
        throw error
      }
      setOrgs([])
      setDraftStatusByOrgId({})
      setRowErrorByOrgId({})
      setErrorMessage(
        formatSuperadminError(error, {
          operation: 'list',
        }),
      )
    } finally {
      if (!isMountedRef.current || sequence !== loadSeqRef.current) {
        return
      }
      if (showLoading) {
        setIsLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    isMountedRef.current = true
    void loadOrgs()

    return () => {
      isMountedRef.current = false
      activeLoadControllerRef.current?.abort()
    }
  }, [loadOrgs])

  const filteredOrgs = useMemo(() => {
    const normalizedName = nameFilter.trim().toLowerCase()
    const normalizedInn = normalizeDigits(innFilter)

    return orgs.filter((org) => {
      const orgName = org.name.toLowerCase()
      const orgInn = normalizeDigits(org.inn ?? '')
      const matchesName = normalizedName.length === 0 || orgName.includes(normalizedName)
      const matchesInn = normalizedInn.length === 0 || orgInn.includes(normalizedInn)
      const matchesStatus = statusFilter === 'all' || org.status === statusFilter
      return matchesName && matchesInn && matchesStatus
    })
  }, [innFilter, nameFilter, orgs, statusFilter])

  async function loadOrganizationById(organizationId: number) {
    setHasTriedView(true)
    setIsViewLoading(true)
    setViewError(null)
    try {
      const response = await getCompany(organizationId)
      if (!isMountedRef.current) {
        return
      }
      setViewResult(response)
    } catch (error) {
      if (!isMountedRef.current) {
        return
      }
      setViewResult(null)
      setViewError(
        formatSuperadminError(error, {
          operation: 'view',
          notFoundMessage: SUPERADMIN_TEXT.organizationNotFound,
        }),
      )
    } finally {
      if (isMountedRef.current) {
        setIsViewLoading(false)
      }
    }
  }

  async function handleCreateOrganization(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedName = createName.trim()
    if (!normalizedName) {
      setCreateError('Enter organization name.')
      setCreateSuccessMessage(null)
      return
    }

    setIsCreating(true)
    setCreateError(null)
    setCreateSuccessMessage(null)
    setCopyFeedback(null)

    try {
      const response = await createCompany(normalizedName)
      if (!isMountedRef.current) {
        return
      }
      setCreatedOrganizationId(response.id)
      setCreateSuccessMessage(`Organization created. ID: ${response.id}.`)
      setCreateName('')
      await loadOrgs({ showLoading: false })
    } catch (error) {
      if (!isMountedRef.current) {
        return
      }
      setCreateError(
        formatSuperadminError(error, {
          operation: 'create',
        }),
      )
    } finally {
      if (isMountedRef.current) {
        setIsCreating(false)
      }
    }
  }

  async function handleOpenOrganizationCard() {
    if (createdOrganizationId == null) {
      return
    }
    const nextId = String(createdOrganizationId)
    setViewOrganizationId(nextId)
    setInviteOrganizationId(nextId)
    setCreditsOrganizationId(nextId)
    await loadOrganizationById(createdOrganizationId)
  }

  async function handleCopyOrganizationId() {
    if (createdOrganizationId == null) {
      return
    }
    const copied = await copyTextWithFallback(String(createdOrganizationId))
    setCopyFeedback(
      copied
        ? { kind: 'success', text: 'ID copied.' }
        : { kind: 'error', text: 'Clipboard unavailable. Select and copy ID manually.' },
    )
  }

  async function handleViewOrganization(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedValue = normalizeDigits(viewOrganizationId)
    if (!normalizedValue) {
      setViewError('Enter organization ID.')
      setViewResult(null)
      setHasTriedView(true)
      return
    }
    const organizationId = Number(normalizedValue)
    if (!Number.isInteger(organizationId) || organizationId <= 0) {
      setViewError('Organization ID must be a positive number.')
      setViewResult(null)
      setHasTriedView(true)
      return
    }
    setViewOrganizationId(String(organizationId))
    setInviteOrganizationId(String(organizationId))
    setCreditsOrganizationId(String(organizationId))
    await loadOrganizationById(organizationId)
  }

  async function handleInviteOrganizationAdmin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedOrganizationId = normalizeDigits(inviteOrganizationId)
    const organizationId = parsePositiveInteger(normalizedOrganizationId)
    if (organizationId == null) {
      setInviteFeedback({
        kind: 'error',
        text: 'Organization ID must be a positive number.',
      })
      setInviteToken(null)
      setInviteLink(null)
      return
    }

    const normalizedEmail = normalizeEmail(inviteEmail)
    if (!isValidBasicEmail(normalizedEmail)) {
      setInviteFeedback({
        kind: 'error',
        text: 'Enter a valid admin email.',
      })
      setInviteToken(null)
      setInviteLink(null)
      return
    }

    setIsInviting(true)
    setInviteFeedback(null)
    setInviteToken(null)
    setInviteLink(null)
    setInviteOrganizationId(String(organizationId))
    setInviteEmail(normalizedEmail)

    try {
      const response = await inviteCompanyAdmin(organizationId, normalizedEmail)
      if (!isMountedRef.current) {
        return
      }
      setInviteFeedback({
        kind: 'success',
        text: SUPERADMIN_TEXT.inviteSent,
      })
      setInviteToken(response.token ?? null)
      setInviteLink(response.link ?? null)
    } catch (error) {
      if (!isMountedRef.current) {
        return
      }
      setInviteFeedback({
        kind: 'error',
        text: formatSuperadminError(error, {
          operation: 'invite',
          notFoundMessage: SUPERADMIN_TEXT.organizationNotFound,
        }),
      })
    } finally {
      if (isMountedRef.current) {
        setIsInviting(false)
      }
    }
  }

  async function submitCreditsPayload(payload: CreditRequestPayload) {
    setIsCreditsSubmitting(true)
    setCreditsFeedback(null)

    try {
      const response = await addCredits(payload.companyId, {
        amount: payload.amount,
        reason: payload.reason,
        idempotency_key: payload.idempotency_key,
      })
      if (!isMountedRef.current) {
        return
      }
      setCreditsFeedback({
        kind: 'success',
        text: formatCreditsSuccessMessage(response.id),
      })
    } catch (error) {
      if (!isMountedRef.current) {
        return
      }
      if (isCreditsDuplicateIdempotencyConflict(error)) {
        setCreditsFeedback({
          kind: 'success',
          text: SUPERADMIN_TEXT.creditsAlreadyProcessed,
        })
        return
      }
      setCreditsFeedback({
        kind: 'error',
        text: formatSuperadminError(error, {
          operation: 'credits',
          notFoundMessage: SUPERADMIN_TEXT.organizationNotFound,
        }),
      })
    } finally {
      if (isMountedRef.current) {
        setIsCreditsSubmitting(false)
      }
    }
  }

  async function handleAddCredits(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedOrganizationId = normalizeDigits(creditsOrganizationId)
    const organizationId = parsePositiveInteger(normalizedOrganizationId)
    if (organizationId == null) {
      setCreditsFeedback({
        kind: 'error',
        text: 'Organization ID must be a positive number.',
      })
      return
    }

    const normalizedAmountValue = normalizeDigits(creditsAmount)
    const amount = parsePositiveInteger(normalizedAmountValue)
    if (amount == null) {
      setCreditsFeedback({
        kind: 'error',
        text: 'Amount must be a positive integer.',
      })
      return
    }

    const normalizedReason = creditsReason.trim()
    if (!normalizedReason) {
      setCreditsFeedback({
        kind: 'error',
        text: 'Enter credits reason.',
      })
      return
    }

    setCreditsOrganizationId(String(organizationId))
    setCreditsAmount(String(amount))
    setCreditsReason(normalizedReason)

    const payload: CreditRequestPayload = {
      companyId: organizationId,
      amount,
      reason: normalizedReason,
      idempotency_key: generateIdempotencyKey(),
    }
    setLastSentCreditsPayload(payload)
    await submitCreditsPayload(payload)
  }

  async function handleRetryCredits() {
    if (!lastSentCreditsPayload) {
      return
    }
    await submitCreditsPayload(lastSentCreditsPayload)
  }

  function handleNewCreditRequest() {
    setCreditsOrganizationId('')
    setCreditsAmount('')
    setCreditsReason('')
    setCreditsFeedback(null)
    setLastSentCreditsPayload(null)
  }

  async function handleSaveStatus(org: SuperadminOrg) {
    const nextStatus = draftStatusByOrgId[org.id] ?? org.status
    const isSaving = Boolean(isSavingByOrgId[org.id])
    if (isSaving || nextStatus === org.status) {
      return
    }

    setIsSavingByOrgId((prev) => ({ ...prev, [org.id]: true }))
    setRowErrorByOrgId((prev) => ({ ...prev, [org.id]: null }))

    try {
      await updateOrgStatus(org.id, nextStatus)
      await loadOrgs({ showLoading: false })
    } catch (error) {
      if (!isMountedRef.current) {
        return
      }
      setDraftStatusByOrgId((prev) => ({ ...prev, [org.id]: org.status }))
      setRowErrorByOrgId((prev) => ({
        ...prev,
        [org.id]: formatSuperadminError(error, { operation: 'status' }),
      }))
    } finally {
      if (isMountedRef.current) {
        setIsSavingByOrgId((prev) => ({ ...prev, [org.id]: false }))
      }
    }
  }

  return (
    <main className="screen">
      <section className="card">
        <h1 className="card__title">Superadmin</h1>
        <p className="card__subtitle">Organizations</p>

        <div className="form">
          <label className="label" htmlFor="org-filter-name">
            Filter by name
          </label>
          <input
            id="org-filter-name"
            className="input"
            type="text"
            value={nameFilter}
            onChange={(event) => setNameFilter(event.target.value)}
            placeholder="Organization name"
            autoComplete="off"
          />

          <label className="label" htmlFor="org-filter-inn">
            Filter by inn
          </label>
          <input
            id="org-filter-inn"
            className="input"
            type="text"
            value={innFilter}
            onChange={(event) => setInnFilter(normalizeDigits(event.target.value))}
            placeholder="INN digits"
            inputMode="numeric"
            autoComplete="off"
          />

          <label className="label" htmlFor="org-filter-status">
            Filter by status
          </label>
          <select
            id="org-filter-status"
            className="input"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
          >
            <option value="all">all</option>
            {ORG_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>

          <button
            className="button button--secondary"
            type="button"
            onClick={() => {
              setNameFilter('')
              setInnFilter('')
              setStatusFilter('all')
            }}
          >
            {SUPERADMIN_TEXT.resetFilters}
          </button>
        </div>

        {isLoading ? <p className="card__subtitle">{SUPERADMIN_TEXT.loadingOrganizations}</p> : null}
        {!isLoading && errorMessage ? (
          <>
            <p className="message message--error">{errorMessage}</p>
            <button
              className="button button--secondary"
              type="button"
              onClick={() => {
                void loadOrgs()
              }}
            >
              {SUPERADMIN_TEXT.retry}
            </button>
          </>
        ) : null}
        {!isLoading && !errorMessage && orgs.length === 0 ? (
          <p className="card__subtitle">{SUPERADMIN_TEXT.emptyOrganizations}</p>
        ) : null}
        {!isLoading && !errorMessage && orgs.length > 0 && filteredOrgs.length === 0 ? (
          <p className="card__subtitle">{SUPERADMIN_TEXT.emptyFilteredOrganizations}</p>
        ) : null}
        {!isLoading && !errorMessage && filteredOrgs.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>id</th>
                <th>name</th>
                <th>inn</th>
                <th>phone</th>
                <th>status</th>
                <th>created_at</th>
                <th>actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredOrgs.map((org) => {
                const draftStatus = draftStatusByOrgId[org.id] ?? org.status
                const isSaving = Boolean(isSavingByOrgId[org.id])
                const hasChange = draftStatus !== org.status
                const rowError = rowErrorByOrgId[org.id]
                return (
                  <tr key={org.id}>
                    <td>{org.id}</td>
                    <td>{org.name}</td>
                    <td>{org.inn ?? '-'}</td>
                    <td>{org.phone ?? '-'}</td>
                    <td>
                      <select
                        className="input"
                        value={draftStatus}
                        disabled={isSaving}
                        onChange={(event) => {
                          const nextStatus = event.target.value as OrgStatus
                          setDraftStatusByOrgId((prev) => ({
                            ...prev,
                            [org.id]: nextStatus,
                          }))
                          setRowErrorByOrgId((prev) => ({ ...prev, [org.id]: null }))
                        }}
                      >
                        {ORG_STATUSES.map((status) => (
                          <option key={status} value={status}>
                            {status}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>{formatCreatedAt(org.created_at)}</td>
                    <td>
                      <button
                        className="button button--secondary"
                        type="button"
                        disabled={isSaving || !hasChange}
                        onClick={() => {
                          void handleSaveStatus(org)
                        }}
                      >
                        {isSaving ? 'Saving...' : 'Save'}
                      </button>
                      {rowError ? <p className="message message--error">{rowError}</p> : null}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : null}

        <h2 className="card__title">Admin actions (Organizations)</h2>

        <h3 className="card__subtitle">Create organization</h3>
        <form className="form" onSubmit={handleCreateOrganization}>
          <label className="label" htmlFor="create-organization-name">
            Organization name
          </label>
          <input
            id="create-organization-name"
            className="input"
            type="text"
            value={createName}
            onChange={(event) => setCreateName(event.target.value)}
            placeholder="Enter organization name"
            autoComplete="off"
          />
          <button className="button button--secondary" type="submit" disabled={isCreating}>
            {isCreating ? 'Creating...' : 'Create organization'}
          </button>
        </form>
        {createError ? <p className="message message--error">{createError}</p> : null}
        {createSuccessMessage ? (
          <p className="message message--success">{createSuccessMessage}</p>
        ) : null}
        {createdOrganizationId != null ? (
          <div className="form">
            <p className="hint">Organization ID: {createdOrganizationId}</p>
            <button
              className="button button--secondary"
              type="button"
              onClick={() => {
                void handleOpenOrganizationCard()
              }}
            >
              Open organization card
            </button>
            <button
              className="button button--secondary"
              type="button"
              onClick={() => {
                void handleCopyOrganizationId()
              }}
            >
              Copy ID
            </button>
            {copyFeedback ? <p className={feedbackClassName(copyFeedback.kind)}>{copyFeedback.text}</p> : null}
          </div>
        ) : null}

        <h3 className="card__subtitle">View organization by ID</h3>
        <form className="form" onSubmit={handleViewOrganization}>
          <label className="label" htmlFor="view-organization-id">
            Organization ID
          </label>
          <input
            id="view-organization-id"
            className="input"
            type="text"
            value={viewOrganizationId}
            onChange={(event) => setViewOrganizationId(normalizeDigits(event.target.value))}
            placeholder="Enter organization ID"
            inputMode="numeric"
            autoComplete="off"
          />
          <button className="button button--secondary" type="submit" disabled={isViewLoading}>
            {isViewLoading ? 'Loading...' : 'View organization by ID'}
          </button>
        </form>
        {viewError ? <p className="message message--error">{viewError}</p> : null}
        {hasTriedView && !isViewLoading && !viewError && !viewResult ? (
          <p className="card__subtitle">{SUPERADMIN_TEXT.emptyViewedOrganization}</p>
        ) : null}
        {viewResult ? (
          <div className="form">
            <p className="hint">Organization ID: {viewResult.company.id}</p>
            <p className="hint">Organization name: {viewResult.company.name}</p>
            <p className="hint">Balance: {viewResult.balance ?? '-'}</p>
            {viewResult.last_ledger_entry ? (
              <>
                <p className="hint">Last ledger entry ID: {viewResult.last_ledger_entry.id}</p>
                <p className="hint">Last ledger delta: {viewResult.last_ledger_entry.delta}</p>
                <p className="hint">Last ledger reason: {viewResult.last_ledger_entry.reason}</p>
                <p className="hint">
                  Last ledger created_at: {formatCreatedAt(viewResult.last_ledger_entry.created_at)}
                </p>
              </>
            ) : (
              <p className="hint">Last ledger entry: -</p>
            )}
          </div>
        ) : null}

        <h3 className="card__subtitle">Invite organization admin</h3>
        <form className="form" onSubmit={handleInviteOrganizationAdmin}>
          <label className="label" htmlFor="invite-organization-id">
            Organization ID
          </label>
          <input
            id="invite-organization-id"
            className="input"
            type="text"
            value={inviteOrganizationId}
            onChange={(event) => setInviteOrganizationId(normalizeDigits(event.target.value))}
            placeholder="Enter organization ID"
            inputMode="numeric"
            autoComplete="off"
          />

          <label className="label" htmlFor="invite-organization-email">
            Admin email
          </label>
          <input
            id="invite-organization-email"
            className="input"
            type="email"
            value={inviteEmail}
            onChange={(event) => setInviteEmail(event.target.value)}
            placeholder="admin@example.com"
            autoComplete="off"
          />

          <button className="button button--secondary" type="submit" disabled={isInviting}>
            {isInviting ? 'Sending...' : 'Invite organization admin'}
          </button>
        </form>
        {inviteFeedback ? (
          <p className={feedbackClassName(inviteFeedback.kind)}>{inviteFeedback.text}</p>
        ) : null}
        {inviteToken ? <p className="hint">Invite token: {inviteToken}</p> : null}
        {inviteLink ? <p className="hint">Invite link: {inviteLink}</p> : null}

        <h3 className="card__subtitle">Add credits</h3>
        <form className="form" onSubmit={handleAddCredits}>
          <label className="label" htmlFor="credits-organization-id">
            Organization ID
          </label>
          <input
            id="credits-organization-id"
            className="input"
            type="text"
            value={creditsOrganizationId}
            onChange={(event) => setCreditsOrganizationId(normalizeDigits(event.target.value))}
            placeholder="Enter organization ID"
            inputMode="numeric"
            autoComplete="off"
          />

          <label className="label" htmlFor="credits-amount">
            Amount
          </label>
          <input
            id="credits-amount"
            className="input"
            type="text"
            value={creditsAmount}
            onChange={(event) => setCreditsAmount(normalizeDigits(event.target.value))}
            placeholder="Positive integer"
            inputMode="numeric"
            autoComplete="off"
          />

          <label className="label" htmlFor="credits-reason">
            Reason
          </label>
          <input
            id="credits-reason"
            className="input"
            type="text"
            value={creditsReason}
            onChange={(event) => setCreditsReason(event.target.value)}
            placeholder="Reason"
            autoComplete="off"
          />

          <button className="button button--secondary" type="submit" disabled={isCreditsSubmitting}>
            {isCreditsSubmitting ? 'Submitting...' : 'Add credits'}
          </button>
        </form>
        {creditsFeedback ? (
          <p className={feedbackClassName(creditsFeedback.kind)}>{creditsFeedback.text}</p>
        ) : null}
        {creditsFeedback?.kind === 'error' && lastSentCreditsPayload ? (
          <button
            className="button button--secondary"
            type="button"
            disabled={isCreditsSubmitting}
            onClick={() => {
              void handleRetryCredits()
            }}
          >
            {isCreditsSubmitting ? 'Retrying...' : SUPERADMIN_TEXT.retry}
          </button>
        ) : null}
        <button
          className="button button--secondary"
          type="button"
          disabled={isCreditsSubmitting}
          onClick={handleNewCreditRequest}
        >
          {SUPERADMIN_TEXT.newCreditRequest}
        </button>

        <p className="hint">User: {user?.email ?? '-'}.</p>
        <p className="hint">
          <Link to="/chat">Back to chat</Link>.
        </p>
      </section>
    </main>
  )
}
