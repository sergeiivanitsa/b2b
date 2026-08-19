# Итерация 17 — Backend H1: implementation plan

Статус: reviewed design draft / DevFlow planning input; implementation не утверждена
Specification:
docs/development/iterations/iteration-17-company-report-h1-backend.md

Этот stage map сохраняет принятые sequencing/invariants, но после merge
iteration 16 отдельный DevFlow planner обязан сверить актуальный `main`, выдать
exact production/test/fixture manifest, а plan reviewer — утвердить его до
любых runtime-изменений.

## 1. Preconditions

1. Iteration 16 merged.
2. Current main and DEVFLOW_STATE agree.
3. Evidence registry records pass/disabled for finance, tax, bankruptcy,
   owners/privacy and optional-call operations.
4. Runtime manifest is rechecked against current main.
5. PostgreSQL test environment is available for integration checks.

No gate is silently assumed from a transport mock or third-party comparison.

## 2. Stage A — compatibility contracts

1. Add report_version 2 and optional_datasets with legacy-safe defaults.
2. Keep datasets and CompanyReportCompleteness required-only.
3. Update validation to count named required datasets, never all map values.
4. Preserve original v1 hash checks and immutable JSON.
5. Add table-driven v1/v2 and optional lifecycle tests before orchestration.

Completion: old snapshots parse unchanged; all optional combinations leave the
required lifecycle matrix intact.

## 3. Stage B — evidence-gated domain models

1. Add provider-neutral typed TaxInfoFacts, BankruptcyFacts and owner models.
2. Add public coverage states and allowlisted limitation codes.
3. Implement only mappings backed by enabled evidence entries.
4. Leave disabled capabilities not_requested with safe limitations.
5. Keep normalizers pure, Decimal/date exact and raw-free.

Finance unit activation is a separate conditional substage. If evidence is not
accepted, unit remains unknown and money values stay out of H1.

## 4. Stage C — orchestration

1. Extend provider protocol only for enabled optional methods.
2. Request OWNER_BLOCK only when owner schema/privacy/operational gates pass.
3. Execute enabled optional calls with explicit timeout/retry/pagination
   budgets.
4. Persist optional results in optional_datasets and typed facts.
5. Calculate status, completeness and required freshness only from the fixed
   required tuple.
6. Convert optional errors to safe limitations without destroying required
   facts.

Completion: a required-complete report remains complete for every optional
failure/not-found/empty combination.

## 5. Stage D — pure public projection

1. Implement build_company_public_h1(report, policy).
2. Add checked_date_msk_v1 using zoneinfo Europe/Moscow.
3. Add strict block schemas, order, coverage, sources, limitations and neutral
   actions.
4. Generate deterministic Decimal/date display strings in backend.
5. Apply recursive public-field allowlist and forbidden-key tests.
6. Exclude scoring, signals, AI, contacts, manager INNFL, FSSP and internals.

Completion: identical snapshot and policy produce byte-equivalent JSON after
canonical serialization.

## 6. Stage E — resolver and API

1. Extract one public snapshot resolver from existing publication read logic.
2. Implement active-pin verification and fail-closed behavior.
3. Implement latest-eligible complete/partial unpublished fallback that skips
   newer failed/unusable runs and classifies no-run/pending/failed/not-eligible.
4. Use resolver in both public SSR and H1 endpoint.
5. Add GET /company-reports/{inn}/public-h1 with strict response/error mapping.
6. Keep legacy GET/status/create behavior and response schemas unchanged.

Completion: active-publication SSR and endpoint fixtures have the same pinned
report_id, canonical path, checked date, block order, facts and limitations;
latest_unpublished API is noindex and is compared only with SPA fixtures.

## 7. Stage F — verification

Targeted suites first, then:

    python -m pytest services/product_api/tests_unit -q
    python -m pytest services/product_api/tests -q
    python -m pytest services/gateway_api/tests -q
    git diff --check

Also verify:

- no migration unless an unexpected schema requirement is explicitly approved;
- no production raw/secret/contact artifacts;
- no provider call from public read tests;
- current frontend tests remain baseline-compatible even before iteration 18.

## 8. Review and delivery

- Independent code review receives specification, plan, full diff and exact
  test results.
- Blockers are corrected within approved scope.
- Deployment and provider live probes remain separate human-authorized work.
- Commit/push follow repository authorization rules.
