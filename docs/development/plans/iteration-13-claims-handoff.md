# Итерация 13 — Claims handoff: implementation plan

## 1. Exact changed-file manifest

### Documentation/state

| File | Change |
|---|---|
| `docs/development/iterations/iteration-13-claims-handoff.md` | Approved specification. |
| `docs/development/plans/iteration-13-claims-handoff.md` | This plan. |
| `docs/development/DEVFLOW_STATE.yaml` | `planning → implementing → reviewing → ready_for_merge`; branch preserved. |
| `README.md` | Claims handoff endpoints, source link and manual smoke path. |
| `services/web_ui/README.md` | CompanyReport → Claims smoke/refresh/fallback checks. |

### Backend

| File | Change |
|---|---|
| `services/product_api/alembic/versions/0015_claims_company_report_handoff.py` | Nullable FK/index and nullable unique idempotency hash. |
| `services/product_api/src/product_api/models.py` | Two nullable `Claim` columns matching migration. |
| `services/product_api/src/product_api/claims/company_report_handoff.py` | Exact-record validation, hash verification, identity allowlist and typed outcomes. |
| `services/product_api/src/product_api/claims/schemas.py` | Strict preflight/create DTO and source output DTO. |
| `services/product_api/src/product_api/claims/security.py` | Domain-separated HMAC helpers for handoff key and deterministic edit capability. |
| `services/product_api/src/product_api/claims/repository.py` | Linked/idempotent create, concurrent re-read, source snapshot in public Claim output, extraction merge preservation. |
| `services/product_api/src/product_api/routers/public_claims.py` | Authenticated preflight/create routes; unchanged ordinary POST behavior. |
| `services/product_api/tests_unit/test_claims_company_report_handoff.py` | Resolver/projection/privacy/idempotency unit tests. |
| `services/product_api/tests_unit/test_public_claims.py` | Route/auth/error/backward-compatibility unit coverage. |
| `services/product_api/tests/test_claims_company_report_handoff.py` | PostgreSQL linked create, isolation, race and report-update integration tests. |
| `services/product_api/tests/test_claims_handoff_migration.py` | Disposable PostgreSQL migration/schema/legacy-row validation. |
| `services/product_api/tests/test_public_claims.py` | Existing Claims flow regression with nullable source fields. |

No CompanyReport domain/scoring/provider files, Gateway, dependencies, settings,
Compose or deploy configuration change.

### Frontend

| File | Change |
|---|---|
| `services/web_ui/src/companyReport/companyReportTypes.ts` | Remove identity-bearing location-state handoff; retain safe report ID contract. |
| `services/web_ui/src/components/company-report/CompanyReportContent.tsx` | Score-independent CTA and manual fallback CTA states. |
| `services/web_ui/src/components/company-report/CompanyReportContent.test.tsx` | CTA payload/state/a11y tests. |
| `services/web_ui/src/pages/CompanyReportPage.tsx` | Pass source UUID only for eligible report; manual fallback for other states. |
| `services/web_ui/src/pages/CompanyReportPage.test.tsx` | Complete/partial/pending/failed/missing/auth/error CTA behavior. |
| `services/web_ui/src/claims/companyReportHandoff.ts` | UUID query parsing, preflight state and safe backlink helper. |
| `services/web_ui/src/claims/companyReportHandoff.test.ts` | Query/privacy/fallback/backlink tests. |
| `services/web_ui/src/claims/claimsApi.ts` | Preflight and linked-create clients; source fields in Claim DTO. |
| `services/web_ui/src/claims/claimsApi.test.ts` | Exact paths/body/header, no identity payload, errors. |
| `services/web_ui/src/claims/claimSession.ts` | Backward-compatible optional source UUID and handoff command key recovery. |
| `services/web_ui/src/claims/claimSession.test.ts` | Legacy/new session, refresh, invalid data and clear behavior. |
| `services/web_ui/src/pages/ClaimStep1Page.tsx` | Preflight/manual state, linked submit, synchronous double-submit guard and draft reuse. |
| `services/web_ui/src/pages/ClaimStep1Page.test.tsx` | Prefill, auth/error/manual, refresh and duplicate-submit tests. |
| `services/web_ui/src/pages/ClaimStep2Page.tsx` | Source notice and report backlink while preserving editable inputs. |
| `services/web_ui/src/pages/ClaimStep2Page.test.tsx` | Restored prefill, edit/save, backlink and preflight failure tests. |
| `services/web_ui/src/router/AppRouter.claims.test.tsx` | Direct query/manual/auth regression. |
| `services/web_ui/src/index.css` | Scoped CTA, source hint, fallback, focus and responsive styles. |

## 2. Stage 1 — migration and ORM

1. Create append-only revision `0015_claims_company_report_handoff` with
   `down_revision = "0014_company_report_publications"`.
2. Add:
   - `source_company_report_id UUID NULL REFERENCES company_reports(id)
     ON DELETE SET NULL`;
   - index `ix_claims_source_company_report_id`;
   - `handoff_idempotency_key_hash VARCHAR(64) NULL`;
   - unique constraint `uq_claims_handoff_idempotency_key_hash`.
3. Existing Claim rows remain valid with both fields null.
4. Migration test proves upgrade from current head, single head, nullable legacy
   compatibility, FK behavior, uniqueness and downgrade/upgrade on disposable
   PostgreSQL.

## 3. Stage 2 — trusted resolver

Implement `company_report_handoff.py` without provider/network calls.

Resolver must:

1. Select exact `CompanyReportRecord` UUID and its `CompanyReportSubject`.
2. Distinguish missing, pending, failed and identity-unavailable outcomes.
3. Deep-copy `normalized_snapshot` and verify its calculated hash against
   `record.snapshot_hash` before deserialization.
4. Deserialize only a hash-valid snapshot.
5. Require exact correspondence:
   - report UUID equals record UUID;
   - report version equals record version;
   - report status equals record lifecycle status;
   - normalized target identifier equals subject normalized identifier;
   - normalized counterparty INN equals the same subject identifier.
6. Reject fail-closed a snapshot copied from another record even when its
   stored hash was recomputed and is otherwise valid.
7. Select debtor name deterministically from non-empty `short_name`, then
   `full_name`, and emit only supported `debtor_name`/`debtor_inn`.
8. Never inspect or return scoring, signals, explanation, finance,
   arbitration, raw/provider journal or worker data.

## 4. Stage 3 — endpoints, authorization and actor-scoped idempotency

1. Add authenticated GET and POST handoff routes using existing
   `require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER)` and pass
   `current_user` explicitly to linked-create logic.
2. Keep ordinary `POST /claims` unchanged.
3. Validate/canonicalize `Idempotency-Key`.
4. Build separate HMAC inputs with fixed distinct v1 domain separators:
   - stored command hash;
   - deterministic raw edit capability.
5. Bind both inputs to `current_user.id`, exact path `report_id` and canonical
   key. Store only command digest and the existing hash of edit capability.
6. Existing-row reuse:
   - query only the digest computed for the current authenticated actor;
   - verify exact source report UUID and normalized input text;
   - return the same Claim/edit capability only when all match;
   - return safe `409` on semantic mismatch without exposing stored Claim
     details.
7. Cross-user same-key behavior:
   - authorization runs first;
   - a different actor produces different digest/edit capability;
   - if authorized, creates an independent draft;
   - if unauthorized, creates nothing and receives existing `401/403`.
8. Resolve same-actor concurrent insert through nested transaction/savepoint,
   unique constraint and winner re-read under the same actor/report/key digest.
9. Append creation events once and keep their payload limited to report UUID,
   prefilled field codes and safe status metadata.
10. Public Claim snapshot adds nullable `source_company_report_id`; existing
    clients remain compatible.

## 5. Stage 4 — extraction and user editing

1. Seed normalized data with existing empty Claims schema plus server debtor
   fields.
2. During extraction merge, preserve current linked debtor fields over
   extraction output and rebuild `missing_fields`.
3. Do not prefill any debt fact.
4. Existing PATCH remains the only path for user corrections and may
   change/null debtor fields.
5. GET after PATCH returns edited persisted values.
6. Preview/generation/payment/admin flows continue reading the existing
   normalized data contract without CompanyReport calls.

## 6. Stage 5 — frontend

1. Replace iteration 11 location-state identity context with
   `/claims?report_id=<uuid>`.
2. Render CTA independently of scoring and for manual fallback states.
3. Step 1:
   - parse only report UUID;
   - call preflight;
   - render loading/available/manual/error states;
   - keep textarea usable during manual fallback;
   - create/persist one command key before linked submit;
   - guard submit with both synchronous ref and disabled state;
   - restore matching source draft rather than creating one during navigation.
4. After linked create, persist Claim session before extraction.
5. Step 2 restores Claim normally, displays source notice, allows edits and
   uses source UUID preflight to reconstruct a safe company backlink.
6. Failed preflight/backlink calls never delete or block an existing Claim.
7. Ensure labels, live regions, keyboard navigation, focus and mobile layout.

## 7. Required tests

### Backend unit

- complete and partial trusted projection;
- nullable name and absent identity;
- pending, failed, missing and corrupt/hash-mismatch report;
- body extra debtor/name/address/status fields rejected;
- only debtor name/INN emitted;
- no raw/scoring/signals/AI/provider data;
- `401`, inactive `401`, role `403`, allowed member roles and superadmin;
- ordinary public POST unchanged;
- stable HMAC test vectors prove command/edit domain separation;
- changing actor ID, report UUID or canonical key changes both derived values;
- same idempotency key returns same Claim/edit capability;
- mismatched reuse returns `409`;
- two authorized users using the same raw key for the same report create
  independent Claims with different stored digests and edit capabilities;
- cross-user replay cannot retrieve the first actor's Claim or use its edit
  capability;
- unauthorized second actor is rejected before lookup/create;
- snapshot copied from report B into record A and accompanied by its recomputed,
  valid hash is rejected because UUID/subject/target correspondence fails;
- extraction preserves prefilled debtor fields;
- later PATCH edits persist;
- no duplicate creation event.

### PostgreSQL integration

- migration against legacy Claims rows;
- FK/index/unique constraints;
- exact report UUID linked;
- concurrent identical creates produce one Claim;
- same-actor concurrent identical commands create exactly one Claim;
- cross-user identical raw keys do not conflict on the unique digest and create
  separate drafts only when both actors pass report authorization;
- no cross-user response contains the other Claim ID/edit capability;
- swapped immutable snapshots with recomputed valid hashes produce no linked
  Claim and no prefill;
- different command keys may intentionally create different Claims;
- inaccessible/missing/unusable report creates none;
- edit-token isolation between Claims;
- unlinked Claims flow remains functional;
- new report for same subject does not change source FK or copied debtor values;
- FK nulling does not make Claim unreadable;
- persistence/events contain no forbidden report data.

No test performs real DataNewton, Gateway/OpenAI, email or production DB calls.

### Frontend

- CTA text, score independence and minimal URL;
- complete/partial linked transition;
- pending/failed/not-found/auth/error manual fallback;
- preflight display and source hint;
- no client identity in linked POST;
- manual editing and save;
- refresh step 1 and Claim restore step 2;
- matching draft continuation;
- synchronous double-click protection and same retry key;
- loading/error/retry states;
- safe backlink;
- accessible names/live regions/focus;
- existing manual Claims and router tests.

## 8. Verification gate

Targeted backend:

```text
python -m pytest services/product_api/tests_unit/test_claims_company_report_handoff.py services/product_api/tests_unit/test_public_claims.py -q
python -m pytest services/product_api/tests_unit -q -k "claim or company_report"
```

Targeted frontend:

```text
npm run test --prefix services/web_ui -- --run src/claims/companyReportHandoff.test.ts src/claims/claimsApi.test.ts src/claims/claimSession.test.ts src/pages/ClaimStep1Page.test.tsx src/pages/ClaimStep2Page.test.tsx src/components/company-report/CompanyReportContent.test.tsx src/pages/CompanyReportPage.test.tsx src/router/AppRouter.claims.test.tsx
npm exec --prefix services/web_ui -- eslint src/claims/companyReportHandoff.ts src/claims/claimsApi.ts src/claims/claimSession.ts src/pages/ClaimStep1Page.tsx src/pages/ClaimStep2Page.tsx src/components/company-report/CompanyReportContent.tsx src/pages/CompanyReportPage.tsx
```

Disposable PostgreSQL only:

```text
python -m pytest services/product_api/tests/test_claims_handoff_migration.py services/product_api/tests/test_claims_company_report_handoff.py services/product_api/tests/test_public_claims.py services/product_api/tests/test_company_reports_api.py -q
python -m pytest services/product_api/tests -q
```

Alembic from `services/product_api` against the disposable database:

```text
alembic -c alembic.ini heads
alembic -c alembic.ini upgrade head
```

Repository regression:

```text
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
npm run lint --prefix services/web_ui
python -m compileall -q services/product_api/src services/product_api/alembic services/product_api/tests services/product_api/tests_unit
git diff --check
```

Full frontend lint is recorded separately from targeted lint so pre-existing
baseline failures, if any, are reported separately. Docker Compose validation
is not required because configuration is unchanged.

Before commit:

- inspect changed paths for `.env`, secrets, raw fixtures, logs/caches and
  unrelated files;
- scan diff for raw payload/provider headers/keys, scoring/signals/AI
  persistence and unsafe report fields;
- verify one Alembic head and no rewritten historical revision;
- remove disposable PostgreSQL container and volume;
- stage only iteration 13 files;
- run `git diff --cached --check`;
- update state to `ready_for_merge`;
- create exactly one local conventional commit, without push/PR/merge;
- verify clean worktree.

## 9. Completion gate

Iteration is complete only when plan review is approved, implementation and
applicable PostgreSQL checks pass, baseline failures are separated from
introduced failures, independent code review has no blocking/substantial issue
after the single allowed fix pass, the diff is privacy-safe, and the final
local commit contains only the manifest above.
