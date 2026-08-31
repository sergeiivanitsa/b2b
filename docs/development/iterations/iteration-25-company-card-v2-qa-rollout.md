# Итерация 25 — QA и rollout Company Card v2

ID: 25

Slug: `company-card-v2-qa-rollout`

Planning-audit base: `886f207d945e35acc1a7e5c07dcff8c36e501bf6`

Implementation base: `NOT ESTABLISHED — exact post-prerequisite origin/main`

Planning branch: `codex/iteration-25-company-card-v2-qa-rollout`

Implementation branch/worktree: NOT ESTABLISHED — must be created clean from
the post-prerequisite `origin/main`; this draft branch is not rebased.

Статус: `PLANNING-AUDIT REVIEW APPROVED — IMPLEMENTATION BLOCKED`

Planning authorization: owner command to proceed on `2026-08-27`

Planning-audit review: `APPROVED 2026-08-27` — reconciliation, rollout/CAS and
QA/CI scopes; this verdict is bound to the planning-audit base only.

Post-prerequisite implementation review: `REQUIRED ON NEW EXACT BASE`

Owner implementation approval: `NOT ELIGIBLE / NOT GRANTED`

Production activation: `NOT AUTHORIZED`

## 1. Цель

Закрыть только принадлежащие iteration 25 cross-layer и real-browser gates,
реализовать fail-closed control plane для переключения immutable H1/H2 pins и
подготовить воспроизводимый staged rollout без фактического production
действия.

Результат должен доказать одновременно:

- PostgreSQL row → exact pin → API/SSR → embedded DTO → React parity;
- H1/H2 coexistence и обратимый H1 → H2 → H1 CAS;
- полную browser-матрицу для shell, F1–F5 и A1–A5;
- отсутствие paid/provider/read-side/client-telemetry side effects;
- crawler, canonical, robots, sitemap, Claims и asset/release continuity;
- обязательную CI-границу перед manual exact-SHA deploy;
- безопасные seed, preflight, canary, monitoring и rollback procedures.

Passing QA не включает H2 автоматически. H1 остаётся production default, пока
владелец отдельно не одобрит production preflight, deploy и каждый rollout
stage.

## 2. Нормативные источники

В порядке приоритета:

1. Root `AGENTS.md`, `README.md`, Roadmap и `DEVFLOW_STATE.yaml`.
2. `decisions/iteration-25-planning-activation-boundary-v1.md` после owner
   approval; до него документ является proposed decision register.
3. Эта спецификация и independently approved implementation plan.
4. `evidence/iteration-25-company-card-v2/iteration-25-baseline-audit-v1.md`.
5. Iteration 19 sections 6–8, 18–21, 24, 28–30, 34–35.
6. Merged implementation contracts iterations 20–24.
7. Iteration-24 owner decision D1–D6 для current visible arbitration policy.

Roadmap/DEVFLOW являются источником текущего lifecycle. Статусы внутри старых
iteration specs являются историческими checkpoints.

При конфликте:

- iteration-24 D1–D6 supersede старые multi-page, named-opponent, entity-type,
  non-RUB и KAD ожидания только для current policy-v3 projection;
- iteration 25 проверяет только факты, реально публикуемые policy v3;
- hidden/unverified fields не становятся обязательными или видимыми;
- missing/partial/failed/conflict остаются разными состояниями;
- никакой QA fixture не создаёт бизнес-факт, порог, единицу или production
  разрешение.

## 3. Hard prerequisites

### 3.1. До implementation

Перед первым изменением production/runtime/test behavior обязательны:

1. Успешный exact run из чистого merged worktree:

   ```powershell
   pwsh -File scripts/run-iteration24-postgres-tests.ps1
   ```

2. Отдельный reconciliation результата, снимающий только iteration-24
   disposable PostgreSQL debt в Roadmap и `DEVFLOW_STATE.yaml`.
3. Exact iteration-20 presentation-create contract tests and static audit. The
   current merged route is already confirmed to accept query input and return
   less than the frozen complete `PresentationLifecycle`; therefore a separate
   iteration-20 continuation must be specified, reviewed, merged and reconciled.
4. Stop this base-bound draft. After the continuation's human merge, create a
   new clean implementation worktree/feature branch from the exact new
   `origin/main`; do not rebase/reset or silently reuse this draft branch.
   Reapply only the planning documents, update the exact implementation base
   and every base-derived hash/inventory, then rerun the bounded delta audit
   and every Stage-0 check.
5. Repeat independent plan review on that refreshed base and obtain
   `VERDICT: APPROVED`; a review of this pre-prerequisite draft does not
   authorize implementation.
6. Явное owner approval полной reviewed specification/plan.

Планирование и docs review разрешены до пункта 1. Product code, migration,
workflow behavior, package lock и executable scripts до него не меняются.

Если iteration-24 runner выявляет defect, исправление оформляется как
iteration-24 continuation/prerequisite. Оно не включается в scope iteration 25.
The confirmed iteration-20 route correction is likewise external and may not
be hidden inside iteration-25 cross-layer work.

### 3.2. До production action

Даже после готовой реализации обязательны отдельно:

- `VERDICT: READY` независимого end-to-end reviewer;
- явная команда commit/push и human merge;
- read-only production preflight с отдельно выданным разрешением;
- все P1–P9 из decision register;
- отдельные разрешения на seed, deploy/migration, provider/AI operation,
  assignment и indexability.

## 4. Scope

### 4.1. Rollout control plane

- New immutable active H2 pin generations, noindex и indexable modes.
- Explicit persisted H2 projection scope for new pins; frozen legacy-pin reads.
- General H1/H2 assignment CAS with independent assignment/pin generations.
- Decision digest and closed stage/reason audit on new journal transitions.
- Operator-only dry-run/plan/apply/rollback/status CLI.
- Exact H1 rollback-pin preflight and idempotent resume.
- H1/H2 assignment-aware sitemap and canonical selection.

### 4.2. Cross-layer QA

- Full Product API unit and PostgreSQL integration suites.
- Full Gateway suite without live model access.
- Web lint, Vitest, TypeScript/build/manifest and bundle gates.
- PostgreSQL → real Product API → HTTP → Playwright Chromium E2E.
- Release/nginx/asset history and deployment-order rehearsal.
- Claims exact-report target continuity.

Unit/contract tests may be added for the new rollout control plane and new
cross-layer adapters. They may not be used to hide a missed mandatory matrix
from iterations 20–24.

### 4.3. Browser and accessibility

- Required seven widths and explicit interaction overlays.
- Full factual SSR, React hydration and lazy finance/arbitration chart success.
- Lazy-chunk failure fallback.
- Keyboard, touch, 200% zoom, reduced motion and simulated non-zero safe area.
- Deterministic screenshot comparisons in a pinned environment.
- Automated accessibility scan plus explicit semantic/focus assertions.

### 4.4. CI and release safety

- Required QA workflow with exact-SHA aggregator.
- Manual protected-environment production workflow only.
- One immutable SHA across RU Product, worker, Gateway, Web and assets.
- Strict worker drain, migration preflight, atomic Web release and rollback.
- Initial/DR H2 asset seed tooling and disposable rehearsal.
- Runbooks and privacy-safe aggregate operational status.

## 5. Вне scope

- Actual production DB query, backup, migration, seed, deploy or rollback.
- Actual production flag, assignment, sitemap/indexability or percentage change.
- Live DataNewton/FNS/Gateway/OpenAI request or paid smoke.
- Automatic H2 generation, refresh, backfill or mass republish.
- Public/admin HTTP assignment mutation.
- Browser-controlled writer/profile/version/cohort selection.
- H1 removal or semantic/byte rewrite.
- Changes to Claims form/auth/storage/business semantics.
- New signals, scoring, verdict, probability, recommendations or thresholds.
- Fixing unrelated dependency vulnerabilities or baseline failures.
- New provider fields, datasets, units, finance formulas or arbitration meaning.
- Named opponents, entity inference, KAD, non-RUB/FX or multi-request pagination.
- Invented production SLOs, rollout percentages, budgets or key material.

## 6. Immutable invariants

### 6.1. H1 remains permanent

- `POST /company-reports` remains permanently H1/v2 only.
- H1 pins, DTO, SSR renderer, canonical behavior and Claims handoff remain
  backward compatible.
- An H2 rollout flag never changes an existing H1 job/report/pin.
- No cookie, header, query or browser state selects H1/H2.
- Missing assignment continues to mean H1.

### 6.2. Reads remain side-effect free

Every H1/H2 API, canonical GET/HEAD, wrong-slug request, robots, sitemap,
crawler and browser read performs only bounded database reads and local
deterministic rendering. It performs no:

- report/presentation/pin/assignment creation;
- provider/FNS/Gateway/AI call;
- budget reservation, queue or worker action;
- Claims mutation;
- client telemetry, Webvisor or session replay;
- refresh/backfill or selection of a newer report.

### 6.3. Facts remain immutable and exact

- Root report ID, pin report ID, visible ID and both Claims paths are exact.
- Snapshot/chart/projection/narrative hashes are revalidated at every
  activation and read boundary.
- Decimal facts remain strings/`Decimal`; browser number conversion is limited
  to bounded geometry ratios.
- Missing never becomes zero, no-cases, negative or positive conclusion.
- Partial collection never becomes complete and never extrapolates.
- No raw provider payload or private identifier enters public DTO, HTML, DOM,
  logs, metrics, screenshots or CI artifacts.

## 7. Authorization phases

### Phase A — default-off implementation

Allowed after implementation approval:

- code, migration and CI changes in the feature worktree;
- synthetic fixtures and disposable PostgreSQL;
- loopback Product API/browser/release rehearsal;
- no production secrets or network beyond package/browser installation in CI.

All repository defaults remain:

```text
COMPANY_CARD_V2_PRESENTATIONS_ENABLED=false
COMPANY_CARD_V2_WRITER_ENABLED=false
COMPANY_CARD_V2_ROLLOUT_GENERATION=0
COMPANY_CARD_V2_ALLOWLIST_INNS=[]
COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS=0
COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED=false
COMPANY_CARD_AI_NARRATIVE_ENABLED=false
COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH=true
daily/monthly credits = 0
narrative concurrency = 0
```

### Phase B — production preparation

Separately authorized read-only preflight, seed and default-off exact-SHA
deploy. A successful deploy still leaves assignments and runtime operations
off. Migration rollback is not a rollout mechanism.

### Phase C — staged activation

Each test/allowlist/percentage/indexable/GA transition consumes a distinct
owner-approved decision digest. No previous approval is reusable as a later
stage.

## 8. Rollout decision contract

The operator tool accepts one strict UTF-8 canonical-JSON decision file. The
parser rejects BOM, duplicate/unknown keys, non-canonical UUID/hex/number forms,
surrogates and input above the technical safety cap of 1,048,576 bytes. A file
contains 1..1,000 targets; these are parser/transaction safety caps, not a
business rollout threshold.

```text
CompanyCardV2RolloutDecisionV1
  schema_version = "company_card_v2_rollout_decision_v1"
  decision_id: canonical UUID
  authorization_reference: 1..128 safe ASCII
  release_commit: exact 40 lowercase hex
  rollout_generation: positive integer | null
  action: "activate" | "rollback"
  stage: "allowlist" | "percentage" | "ga" | "emergency_rollback"
  target_contract: "company_public_h1_v1" | "company_public_h2_v1"
  h2_indexable: boolean
  allowlist_inns: sorted unique 0..1000 normalized INNs | null
  percentage_basis_points: integer 0..10000 | null
  maximum_batch_size: integer 1..1000
  observation_window_seconds: positive integer | null
  abort_policy_reference: 1..128 safe ASCII | null
  targets: strictly ordered unique target objects
```

`validate`, `plan` and `status` are CLI modes, never persisted decision actions.
The action/stage matrix is closed:

| Action/stage | Cohort fields | Target/indexability | Observation fields |
|---|---|---|---|
| `activate/allowlist` | positive generation, nonempty sorted allowlist, percentage `0`; every target is in the allowlist | H2; noindex only when current H1 is not indexable, otherwise indexable + P9 | positive window + abort reference |
| `activate/percentage` | positive generation, sorted allowlist (possibly empty), percentage `1..9999`; every target is allowlisted or satisfies the frozen bucket rule | H2; no indexable-H1 deindex, P9 for indexable | positive window + abort reference |
| `activate/ga` | positive generation, live sorted allowlist, percentage `10000` | H2 indexable only, P9 | positive window + abort reference |
| `rollback/emergency_rollback` | generation/allowlist/percentage all null and ignored live | exact current H2 → exact H1, `h2_indexable=false` | both null |

Any other pair or nullability shape is invalid. `targets.length` must not exceed
`maximum_batch_size`; P3 may choose a smaller value but cannot exceed the
technical cap.

Every target has exactly these common fields:

```text
subject_id: canonical UUID
inn: normalized 10/12-digit INN
expected_assignment_generation: integer >= 0
expected_current_contract: null | "company_public_h1_v1" | "company_public_h2_v1"
expected_current_pin_generation: positive integer | null
```

Generation `0` requires both current fields null; a positive generation
requires both non-null. Activate targets additionally contain exactly
`source_h2_pin_generation`, `expected_active_h2_pin_generation`,
`expected_active_projection_digest` and `h1_rollback_pin_generation`.
Rollback targets instead contain exactly `h1_target_pin_generation`; their
expected current contract is H2. All pin generations are positive and the
digest is 64 lowercase hex.

Targets are strictly increasing by normalized INN and have unique INN and
subject ID. Processing order is exactly file order. The complete decision is
validated, canonicalized, cohort-membership checked and bound to its digest
before the first target mutation. On the first non-idempotent target failure,
the batch stops; it never skips ahead. Status reports target ordinal plus a
closed code. Resume uses the exact same decision: already-current journal
results are idempotent, untouched later ordinals proceed, and a superseded
result stops as conflict.

A decision file may contain production identifiers and therefore:

- is never committed;
- is never uploaded as a generic CI/browser artifact;
- is read from an owner-controlled local path;
- is represented in DB/log output only by `decision_id`, SHA-256 digest and
  closed non-sensitive codes.

`plan` is read-only. `apply`/`rollback` require both the file and an exact
`--confirm-digest` value. Release/config mismatch, absent P inputs, wrong SHA,
bad target, stale assignment generation or mixed subject/pin lineage fail
before that target mutates.

For `activate`, rollout generation is positive, allowlist/percentage are
present and must equal the live fail-closed cohort configuration. For
`rollback|emergency_rollback`, those three fields may be null and are never
compared with live writer/presentation/cohort flags. Rollback remains available
after flags are closed or percentage/generation is reset; it requires only the
authorized exact release/tool, current assignment, H1 pin and CAS fence and
performs no provider/AI operation.

The Product runtime receives optional nonsecret `PRODUCT_RELEASE_COMMIT`. It is
absent in ordinary local/default-off use and must be exact 40 lowercase hex
when supplied. Any rollout mutation requires it and requires byte equality
with `release_commit` in the decision; reading a git checkout or image tag by
guess is forbidden.

Percentage membership reuses exactly the frozen
`company-card-v2-cohort-v1\0{inn}` SHA-256 rule. The operator tool does not
create H2 reports or pins by calling provider/AI and does not turn percentage
membership into automatic backfill. It can activate only already valid pins.

For H2 activation, read-only `plan` calculates the exact expected active pin
identity and projection digest from the locked-current view without writing:
the byte-identical existing active generation when idempotent reuse is valid,
otherwise the exact next generation. `apply` rechecks that choice and, in one
transaction, reuses or appends that exact active pin and performs assignment
CAS. Any concurrent pin or assignment change rolls back both operations; no
orphan active pin is committed.

## 9. Persistence and migration contract

Iteration 25 adds one append-only revision `0019` after `0018`.

### 9.1. Pin scope and active shapes

Add a nullable closed `projection_scope` column to presentation pins:

- existing rows remain null and retain historical resolution behavior;
- new H1 pins remain null;
- new H2 staged pins use `staged_publication`;
- new H2 active pins use `active_publication`.

The H2 pin DB constraint admits only:

1. historical/staged noindex shape with no canonical/lastmod;
2. new staged noindex scope with no canonical/lastmod;
3. new active resolved shape with exact canonical/lastmod and boolean
   indexability.

Only resolved report-version-3/policy-v3 pins may become active. An active H2
pin is always appended; staged/historical pins are not mutated. Its projection
digest is rebuilt from the exact active scope, canonical path and indexability.

`published_lastmod` is the immutable report `generated_at`, never hidden
current time or activation time.

### 9.2. Assignment journal audit

Add `company_card_v2_rollout_decisions` as a non-sensitive global binding:

```text
decision_id primary key
decision_digest unique
schema_version
release_commit
action
stage
target_contract
h2_indexable
target_count
```

The pair `(decision_id, decision_digest)` is also an explicit unique key for
the journal composite foreign key.

All fields are closed/validated; the table stores no INN, subject, URL,
authorization reference or decision body. The advisory-lock derivation is
normative Python semantics; the separator is one NUL byte (`0x00`), not the two
ASCII bytes backslash/zero:

```python
domain = b"company-card-v2-rollout-decision-v1\x00"
digest = hashlib.sha256(domain + decision_id.encode("ascii")).digest()
key = int.from_bytes(digest[:8], "big", signed=True)
```

Frozen vector:

```text
decision_id = 00000000-0000-0000-0000-000000000000
preimage_hex = 636f6d70616e792d636172642d76322d726f6c6c6f75742d6465636973696f6e2d76310030303030303030302d303030302d303030302d303030302d303030303030303030303030
sha256 = 2fa1cd1f624ee2b6e6a211f74f9905f0259e49fd040c99bfd840f726ab295ed8
signed_int64_key = 3432249925710045878
pg_locks_classid = 799132959
pg_locks_objid = 1649337014
pg_locks_objsubid = 1
```

After complete read-only validation and before any binding/target mutation,
`apply/rollback` creates a one-invocation SQLAlchemy async engine with
`NullPool`, acquires exactly one physical connection and records its
`pg_backend_pid()`. The shared Product engine is forbidden. That same pinned
connection, with no reconnect/recheckout/retry, performs all of the following
in sequence:

1. one connection-owned acquisition transaction records
   `pg_backend_pid()` and calls nonblocking session-level
   `pg_try_advisory_lock(key)`, then commits; the session lock survives that
   transaction commit;
2. the short global-binding insert-or-compare transaction;
3. every per-target transaction, using sessions bound to this connection;
4. one connection-owned unlock transaction, then physical close.

`false` from acquisition closes the connection and fails closed as
`decision_in_progress`. After the acquisition transaction exits,
`connection.in_transaction()` must be false. The binding and each target use a
separate connection-owned `connection.begin()` boundary; their bound ORM
session uses `expire_on_commit=false`, only flushes/closes, never calls
`commit()` and never owns or extends the connection transaction; the closed
outcome is materialized before the boundary exits, with no later lazy load.
The PID/lock guard is the first statement **inside** each such transaction and
checks that `pg_backend_pid()` still equals the recorded PID and that
`pg_locks` contains the granted `ExclusiveLock` advisory row for that PID,
`objsubid=1`, and the unsigned high/low 32-bit halves of the key bits. A query
error, invalidated/reconnected connection, PID change or missing lock stops
without retry or a next mutation as `rollout_lock_lost`. If the backend dies
during a target, PostgreSQL rolls that transaction back or its durable journal
records the committed result; the invocation never starts another target.
Thus one `decision_id` cannot be reused with another binding across subjects
or concurrent processes, and a completed prefix remains explicit/idempotent.
On every normal commit or handled rollback, the connection-owned context must
exit and `connection.in_transaction()` must again be false before inspecting
the stop flag or admitting the next target. No query is allowed between these
boundaries. The explicit unlock query likewise runs in its own final
connection-owned transaction so SQLAlchemy autobegin cannot leak an outer
transaction into close/cleanup.

Before lock acquisition, the CLI installs a controlled SIGTERM handler and
restores the previous handler at exit. SIGTERM or task cancellation atomically
closes admission of new targets. The current target task is awaited through
its transaction cleanup; repeated SIGTERM/cancellation cannot cancel the
separate cleanup task. Cleanup is awaited under `asyncio.shield` with a finite,
explicitly tested technical timeout. A mandatory `finally` calls
`pg_advisory_unlock(key)` and accepts only `true`, then closes the physical
connection and disposes the `NullPool` engine. On timeout, connection loss,
unlock error/false, cancellation during close or invalidate/close failure, the
non-awaitable asyncpg physical-driver `terminate()` fallback is invoked before
exit. No connection is returned to a pool. Only after cleanup completes does
the runner propagate cancellation or exit `143` for SIGTERM.

Unit and real-PostgreSQL tests cover the frozen vector, success, contention,
binding/target exception, cancellation, repeated cancellation/SIGTERM, unlock/
invalidate/close failures, physical fallback and same-decision retry. A
disposable PostgreSQL test terminates the recorded backend PID between targets:
the first process must emit `rollout_lock_lost` before the next mutation, the
exact PID/lock must disappear, and a second process must immediately reacquire
and resume from the durable prefix. Another regression commits target N,
forces target N+1 to roll back and proves from a separate observer connection
that N remains durable, N+1 is absent and the pinned connection reported
`in_transaction() == false` at the between-target boundary.

Add nullable legacy-compatible fields to the assignment journal:

```text
decision_id
decision_digest
reason_code
```

All three are null for historical rows or all three are valid for new
iteration-25 transitions. The digest is 64 lowercase hex, reason is a closed
stage/action enum, and `(assignment_id, decision_digest)` is unique for new
rows. A composite journal foreign key to the global `(decision_id,
decision_digest)` binding prevents local mismatch. Database subject/pin foreign
keys remain the target identity boundary.

No production identifier or authorization file body is copied into the
journal.

### 9.3. Migration compatibility

- Upgrade adds only the non-sensitive decision-binding table plus the named
  constraints/columns; no report, pin or assignment is rewritten.
- Legacy H1/H2 rows remain readable byte-for-byte.
- Downgrade is tested only on disposable legacy/no-new-transition states and
  refuses to discard **any** pin with non-null `projection_scope` or any
  journal row with a new audit field or any global decision binding.
- Production rollback keeps `0019` and rolls code/assignment forward/backward;
  it never runs `alembic downgrade`.

## 10. Assignment CAS contract

The operator builds one immutable `CompanyCardV2RolloutTargetCommandV1` per
target. It contains the decision binding, all common expected-current fields
and exactly the action-specific source/active/rollback pin fields defined in
section 8. There is no smaller CAS input that can silently rediscover a pin.

The one target transaction uses this global lock order:

```text
CompanyReportSubject
  -> current assignment + decision journal
  -> H1/H2 pins ordered by (presentation_contract, generation)
  -> exact report + narrative artifact required by those pins
```

Neither `append_active_h2_pin` nor an assignment helper acquires locks before
the subject; both operate on the already locked command/context owned by the
same transaction. One transaction then:

1. locks the stable `CompanyReportSubject` row, which serializes concurrent
   first-assignment inserts as well as updates;
2. loads the current assignment and any journal row for the decision digest;
3. if that journal result is still the exact current assignment, returns
   idempotent success even though the decision's old expected generation is now
   stale; if a later assignment superseded it, returns `decision_superseded`
   without replaying the old transition; mismatched journal identity is corruption;
4. only for a decision not previously applied, requires current assignment
   generation to equal the caller expectation (`0` when absent);
5. loads every exact command pin/report and, for H2, exact narrative/artifact
   in the global order; validates whether the expected active generation is an
   existing byte-identical reusable pin or the exact next append slot;
6. validates subject, report, snapshot, chart, evidence, policy, projection,
   canonical, Claims and indexability lineage;
7. for H2, proves the decision target contains a valid immutable H1 rollback pin;
8. returns closed `already_target` without mutation when a later decision names
   the exact currently assigned pin;
9. appends/reuses the active H2 pin when applicable, appends one journal row
   and advances assignment generation by exactly one only for an actual switch;
10. commits atomically for that subject.

Target pin generation is never compared to assignment generation. A CAS
conflict produces a closed `presentation_assignment_conflict` and no partial
change.

A batch is the globally bound/advisory-serialized, deterministic sequence of
per-subject atomic target transactions, all run sequentially through the same
session-locked physical connection. Output reports only counts and target
ordinals by closed outcome code plus an opaque decision digest. On the first
new failure or lock loss it stops; a partial prefix is explicit and resumes
only with the same globally bound decision. The tool never calls the target
set globally atomic.

## 11. H2 activation and indexability predicate

An active H2 pin requires:

- exact finalized v3 `complete|partial` report for a noindex test/canary;
- lifecycle `complete` for `indexable=true`;
- policy `company_public_h2_publication_v3` and snapshot schema v3;
- exact subject/target/counterparty INN equality;
- exact snapshot, Chart Facts, evidence and projection digests;
- resolved validated artifact or deterministic fallback binding;
- current all-masked arbitration privacy contract and valid key ID provenance;
- no raw/private/unknown public key or forbidden sink;
- canonical uniqueness and exact Claims target;
- internally consistent coverage, limitations and N/M counters.

For `indexable=true` additionally:

- no coverage `failed`, `conflict`, `gate_closed` or `legacy_unavailable`;
- every visible finance/arbitration gate required by current policy v3 is
  verified; fields hidden by D1–D6 are not reintroduced;
- `missing`, `available_empty` and bounded `partial` carry their exact proven
  scope and limitation;
- no malformed/duplicate-conflict/privacy failure is disguised as a safe
  indexable partial;
- P9 explicitly approves the cohort.

Scoring, H1 thin-content sufficiency and AI stylistic quality are not H2
eligibility inputs.

An indexable H1 subject may never be switched to an active noindex H2 pin.
Default noindex allowlist rehearsal uses synthetic or already non-indexed
subjects. A subject with indexable H1 requires an indexable H2 pin and explicit
P9 approval before H2 assignment.

## 12. Rollout stage machine

| Stage | Required state | Allowed mutation | Exit evidence |
|---|---|---|---|
| test publications | synthetic/staged valid H2, flags default-off outside fixture | no assignment; staged noindex only | full DB/API/browser parity |
| allowlist canary | exact prebuilt H2 pins + exact H1 rollback pins | bounded owner decision; noindex only when H1 is not indexable, otherwise indexable H2 + P9 | smoke + observation window + zero abort condition |
| percentage | sticky cohort, exact finite target plan | per-subject CAS only; no auto-generation; no indexable-H1 deindex | aggregate counts, SLO/abort decision |
| GA | exact approved release and indexability predicate | append active indexable pins and CAS | owner P9 and final observation |
| rollback | exact previously validated H1 pins | per-subject H2 → H1 CAS | canonical/Claims/sitemap smoke |

No stage is entered merely because a configuration value is nonzero. An
observation window and abort policy are required production inputs and remain
unset in repository defaults.

## 13. Acceptance profiles

Tracked fixtures are deterministic, synthetic, bounded and contain no
production raw:

1. `sks_morphology_complete_v1` — sanitized СКС-shaped complete v3 with
   artifact/fallback parity, finance F1–F5 and bounded complete arbitration.
2. `sparse_missing_fallback_v1` — missing optional facts, deterministic
   narrative fallback and explicit non-zero/missing distinctions.
3. `partial_long_limitations_v1` — bounded partial data, long legal/address/
   limitation strings and exact disclosure.
4. `large_n_signed_masked_v1` — finance gaps/zero/negative values and
   arbitration top-20/N-of-M with all-masked opponents.
5. `lazy_failure_v1` — same valid factual DTO as a core profile while one lazy
   finance/arbitration chunk is deterministically failed at the browser layer.

Profile IDs, expected report/pin/digest/coverage/chart/Claims facts and maximum
sizes live in a closed registry. The real name/INN/URLs of СКС are absent.

## 14. Cross-layer parity matrix

For every core profile the test seeds an actual disposable PostgreSQL with:

- immutable H1 report/publication/pin;
- immutable v3 H2 report, narrative binding, staged and active pins;
- exact assignment and journal history needed by the scenario;
- no provider journal raw, secret or external URL.

The matrix proves:

```text
DB report/pin/artifact bytes
  -> assignment-aware joined row
  -> public DTO / canonical SSR
  -> script-safe embedded canonical JSON
  -> React parsed state
  -> visible text, chart fallback/enhancement and Claims links
```

Exact report ID, canonical path, projection/chart/snapshot/narrative hashes,
coverage states, Decimal displays, details/order and Claims target remain
equal. No layer selects latest or a different report.

H1 → H2 → H1 rehearsal additionally hashes immutable report/pin/artifact rows
before and after and requires equality; only assignment/journal rows may grow.

## 15. Real-browser matrix

### 15.1. Core visual cells

The four data profiles run at:

```text
320, 390, 768, 1024, 1199, 1200, 1440 CSS px
```

All 28 cells verify SSR before JavaScript, hydration parity, complete factual
text/table fallback, lazy F1–F5/A1–A5 enhancement, CTA placement, no overlap or
horizontal overflow, focus visibility, target sizes, console/runtime/request
errors, loopback-only network, the post-font zero-shift contract and
deterministic screenshot goldens.

`lazy_failure_v1` runs functionally at all seven widths and proves local error
fallback without loss of factual text/Claims actions or a second factual GET.

### 15.2. Interaction overlays

- Keyboard traversal and activation: `390/1024/1440` for every core profile.
- Real touch context: `390/768` for every core profile.
- 200% browser zoom: `390/1024/1440` for every core profile.
- Reduced motion: `390/1440` for every core profile and lazy failure.
- Safe area: portrait and landscape mobile contexts with a non-zero CSS safe
  area design token; content/CTA remain unobscured.
- JS disabled: one complete and one partial/large-N profile at mobile/desktop.

Automated axe scans run after SSR and after lazy enhancement at representative
mobile/desktop widths. Zero serious/critical violations is required, and any
lower-impact result needs a committed exact allowlist with rationale; no broad
rule disable is allowed.

### 15.3. Visual determinism

- The exact `@playwright/test` package/browser revision runs in the matching
  digest-pinned official Playwright Linux container; the job performs no
  mutable OS/browser install.
- A committed SHA-256 of the normalized container `fc-list` inventory is
  asserted before tests; a font/image change requires explicit golden review.
- Animations/transitions/caret are disabled only by Playwright screenshot
  settings or reduced-motion contract, not by product-only test branches.
- Dynamic clocks, random IDs and production data are absent.
- Baselines are committed only for the new iteration-25 suite and may change
  only via an explicit review command.
- Traces/screenshots/JUnit are uploaded on failure with bounded retention;
  decision files, DB dumps and production identifiers are forbidden.

## 16. SEO, crawler and public routing

The browser/API matrix covers:

- canonical slug exact response;
- plain-INN SPA boundary unchanged;
- wrong slug 301 to exact canonical with `noindex,follow`;
- unknown/missing/pending/failed/corrupt noindex responses;
- active H1, active H2 noindex and active H2 indexable;
- GET/HEAD factual/header parity and no body for HEAD;
- robots exact same-origin sitemap reference;
- sitemap chunk/index stability, sort, uniqueness and lastmod;
- zero H1 duplicate when H2 assignment is active;

Sitemap persistence is bounded in application memory. One SQL overlay applies
the canonical rules per subject: no assignment → valid active H1; assigned H1
→ exact pin; assigned indexable H2 → exact H2; assigned noindex/corrupt H2 → no
row. The index obtains only an aggregate eligible-row count. A chunk query
returns at most the frozen chunk size using deterministic normalized-INN/
canonical/subject ordering and a database-side page boundary; Python never
loads the complete publication set. Count/chunk use the same predicate,
deduplicate per subject in SQL and preserve exact legacy H1 results when no
assignments exist. Empty/out-of-range chunks are stable and corrupt assignments
never fall back to H1.
- zero H2 sitemap entry when active pin is noindex;
- zero provider/Gateway/AI/write/client-telemetry activity for crawler agents.

Sitemap and canonical resolution share the same assignment/pin validation
semantics. A corrupt assigned H2 fails closed and does not fall back to H1 or
latest. Rollback CAS makes H1 visible again on the next committed read.

Sitemap uses an explicit overlay, not an assignments-only union:

```text
no assignment        -> current valid active/indexable H1 publication
assigned H1          -> exact valid/indexable H1 pin
assigned H2 indexable-> exact valid H2 pin
assigned H2 noindex  -> no sitemap row; H1 is suppressed
assigned corrupt pin -> no sitemap row and safe failure; no H1/latest fallback
```

This preserves every legacy/default H1 publication that has no assignment.

## 17. Privacy, network and observability

### 17.1. Browser/client boundary

- Webvisor, session replay and third-party analytics are absent.
- Acceptance traffic contains zero client telemetry.
- Service workers are disabled/unregistered in the harness.
- Every non-loopback request is aborted and fails the test.
- No second factual GET occurs after the canonical document.

### 17.2. Server operational evidence

Iteration 25 may add only privacy-safe aggregate events/status:

```text
event_code
contract
stage/reason code
success/conflict/failure count
latency bucket or bounded aggregate
release/decision digest prefix only when non-identifying
```

Forbidden in logs/metrics/artifacts:

- INN/OGRN/name/report/presentation/subject UUID;
- canonical/arbitrary URL or DOM text;
- narrative, amount, case/opponent identity or HMAC;
- raw decision file, key ID/secret, headers or provider payload.

Client telemetry remains absent. Any future client telemetry is a separately
versioned privacy decision.

## 18. Claims target verification

For H1, staged H2, active noindex H2, active indexable H2 and rollback:

- visible report ID equals exact pinned report ID;
- primary and secondary Claims links equal
  `/claims?report_id={exact displayed report_id}`;
- click produces a main-frame full-document navigation request to that exact
  existing anonymous Claims URL. The browser harness intercepts this loopback
  document request before the destination SPA commits, so it proves navigation
  semantics without loading unrelated site-wide telemetry from `index.html`;
- no Claim is created before the existing explicit form action;
- Claims does not substitute latest/cohort/other presentation report;
- no finance/arbitration/narrative/private field leaks into Claims payload;
- H2 → H1 rollback changes the target only to the exact H1 pinned report.

No Claims production code change is expected. A discovered semantic defect is
a blocker requiring a separately approved scope change.

The zero-client-telemetry assertion covers the Company Card document and all of
its SSR/hydration/lazy requests up to that intercepted navigation. Iteration 25
does not claim or alter telemetry behavior of the separately loaded Claims SPA.

## 19. Provider, AI and privacy-key gates

CI and browser jobs:

- receive no production secrets;
- fail before application import if a paid/provider/SMTP/arbitration credential
  is nonempty or a mandatory secret differs from the exact test placeholder;
  conftests never silently delete an inherited credential;
- keep DataNewton/H2 writer/arbitration/AI flags false and budgets zero;
- use MockTransport/fixtures and an unreachable loopback Gateway target;
- do not start provider, Gateway dispatch or narrative workers in browser E2E;
- allow only the test PostgreSQL/Product/asset loopback endpoints.

All Product unit/integration and Gateway suites install one standard-library
guard before application/provider import. It rejects non-loopback DNS/socket
connects; only the integration suite additionally admits the exact
runner-validated disposable PostgreSQL host/port. Negative tests attempt raw
socket, DNS, stdlib HTTP and HTTPX escape, while positive tests prove only the
declared loopback/DB paths. Wildcards and public endpoints are forbidden.

The Claims-link test stops at the intercepted loopback main-frame request as
specified in section 18; it does not load the generic SPA `index.html` and does
not reinterpret that application's existing Yandex Metrika behavior as Company
Card telemetry.

Production DataNewton and AI modes remain P6/P7. Fallback-only is the safe
default. Paid smoke is never implied by a passing mocked Gateway suite.

H2 activation using arbitration additionally requires P8:

- key ID binds one immutable decoded secret/KMS version;
- secret bytes remain while any queued/running report job or bounded recovery
  path can still perform arbitration with that key;
- public reads, pin validation, rollback and rehearsal use stored masked facts,
  hashes and nonsecret key provenance only; they must never resolve an old
  masking secret merely because an immutable report is retained;
- deletion eligibility requires aggregate proof of zero nonterminal job/lease/
  retry/outbox/reservation reference, terminal stored reports whose masked
  projections verify without the secret, and an immutable nonsecret tombstone
  binding key ID to retired KMS-version metadata;
- if any retained-read path is found to require secret bytes, deletion and P8
  activation stop for a new decision; retention is not silently indefinite;
- preflight verifies IDs/eligibility without printing secret bytes or row IDs;
- same-ID secret rebinding is forbidden.

## 20. Asset seed, deploy and DR

### 20.1. Seed

Add a separately invoked seed/verify path that consumes exactly three verified
release packages. The reviewed pre-iteration-25 baseline is:

| Commit | Product H2 manifest SHA-256 |
|---|---|
| `cfbd37c02c99c569e47806337ed0306c9a722551` | `e48fa51389f5365f9fe445b0c49a0a2224103502a6b742ca1cb9bd705f63a6d6` |
| `867c0d21558dc8e73a0e55a42167b38ced6d6b67` | `506b92be298a1e81d8550dad08c5ce4b5ece8fa3d163a78d286642ec75b4b060` |
| `e7478a2fba9aaca17829c3d99e89e8d83d4b3188` | `97a76daefbb73e1b78935916516fa093f3db5027e09ea44f52df6f63ac18222b` |

Any replacement set requires explicit review.

Seed must:

- require an explicitly approved absolute stable root;
- reject symlink, nonempty/unowned/mis-permissioned or partially initialized roots;
- verify every Product manifest, asset graph and SHA before write;
- copy immutably, fsync, write `current + two predecessors` and atomically
  publish the pointer;
- tolerate interruption before pointer publication without exposing partial state;
- never delete an existing store or overwrite a content collision;
- support read-only verify/select rehearsal and DR restore into a fresh temp root.

The repository implements and tests the tool but does not execute production
seed. The runbook separately proves matching Product image retention; assets
alone are not a code rollback.

### 20.2. Deploy boundary

Production workflow becomes `workflow_dispatch` only, with:

- exact 40-hex SHA input;
- proof that `github.ref`, workflow SHA/ref and fetched default-branch head all
  identify the current protected-main `deploy_prod.yml`; dispatch from another
  branch/fork or an older workflow definition is rejected;
- proof from fetched refs that the exact object is a commit already in the
  protected `refs/heads/main` history, never a PR/unmerged object;
- protected `production` environment;
- whole-deploy concurrency `group: prod-deploy`, `cancel-in-progress: false`;
- complete reusable QA workflow with that same SHA as its one required,
  validated `release_sha`;
- explicit checkout of that SHA in every QA job and full-SHA-bound cache,
  artifacts, checksums, results and canonical QA attestation;
- `qa-required` output whose verified SHA must equal the dispatch input;
- build-once/checksum QA artifacts consumed by deploy without rebuilding from
  caller/default-branch state;
- exact SHA/image verification in RU and US;
- strict drain/stop of report and narrative workers;
- read-only preflight before Alembic;
- additive upgrade only, then exact process recreation/health;
- atomic versioned SPA directory and pointer switch;
- recorded prior compatible image/asset/Web pointers;
- automatic restoration on a later deploy-phase failure where safe;
- no H2 assignment or positive flag as part of deploy.

Repository YAML cannot establish GitHub protection settings. P1 therefore
includes current external evidence that protected main requires the single
`qa-required` status and that the `production` environment requires the
approved reviewers. The runbook verifies evidence identity/freshness and stops
before artifact download when it is absent or mismatched.

No command suppresses worker-stop, migration, image-identity or health errors.

### 20.3. Worker drain protocol

P1 supplies an explicit drain deadline that is checked against configured
worker grace/provider/Gateway timeout bounds; the repository does not invent a
production timeout. Before Alembic, a strict operator script:

1. records old container/image identities, DB clock and aggregate lifecycle
   counts; disables automatic restart for the two old worker containers;
2. sends `SIGTERM` to report and narrative workers, closing new claim/dispatch
   admission; it never uses `SIGKILL` or a stop command that escalates to it;
3. waits for both exact containers to exit, then checks a read-only DB snapshot;
4. permits report jobs only in `queued|succeeded|failed` (`running` count zero);
5. permits narrative outbox only in `pending|processed|terminal` (`leased` zero),
   narrative jobs only outside `leased|dispatching|dispatched|validating|rendered`,
   runtime `leased_count=0`, and reservations only `released|consumed`;
6. treats a committed dispatch marker as safe only after the existing fenced
   path reaches terminal `ambiguous_timeout`, `fallback_finalized`,
   `invalid_output` or `finalized`, has no lease, has consumed (never
   released/reused) its credit and
   has the exact fallback/artifact invariant; no second AI dispatch is allowed;
7. repeats process/DB predicates after a stable polling interval and only then
   permits Alembic.

Queued/pending work may remain because it has no owner or external operation.
If a worker exits with an expired active lease, only an existing exact-old-image
bounded reconciliation path that makes no provider/Gateway call may resolve it;
otherwise deploy stops for incident handling. Deadline expiry, a live process,
reserved credit, active/ambiguous nonterminal state or changing counts is STOP
before migration. The script leaves recorded recovery data and never claims
that killing a container resolved an ambiguous dispatch.

## 21. Performance and bundle gates

Deterministic CI gates:

1. The initial H2 closure contains only manifest entry JS/CSS and no lazy
   finance/arbitration chunk request before its interaction/visibility trigger.
2. All manifest paths and raw/gzip bytes are compared to a committed baseline
   produced in the pinned CI environment.
3. Any positive eager-closure delta fails until a reviewed baseline update
   attributes the exact file/reason; no automatic percentage allowance exists.
4. The browser proxy holds the exact H2 entry module while SSR is asserted and
   `document.fonts.ready` resolves. The harness must prove Layout Shift observer
   support, record `post_font_start = performance.now()`, install a buffered
   observer, then release the module and await explicit hydration plus lazy
   success/error terminal signals.
5. After that terminal signal, the harness waits two stable animation frames,
   merges callback entries with `takeRecords()`, then disconnects and asserts.
   This post-font zero-shift gate fails every positive entry with `startTime >=
   post_font_start`, including `hadRecentInput=true`, and records value/flag/DOM
   sources. Earlier buffered entries are diagnostic; unsupported observation
   is a failure rather than an empty pass. This is not a full CLS-window metric.
6. Lazy success/failure does not resize the reserved factual container.
7. LCP, request counts and timing are recorded diagnostically. They do not
   become a production SLO without P4.

The existing SPA >500 kB warning and npm-audit findings are recorded baseline,
not silently fixed or waived by this iteration. New dev dependencies must not
enter either production bundle.

## 22. CI required gates

One reusable exact-SHA workflow exposes these jobs. `workflow_call` requires a
lowercase 40-hex `release_sha`; PR runs resolve that same single value from the
PR head. A resolver validates it once, and every job checks out that exact
value, verifies `HEAD`, and binds every cache/artifact/result name and manifest
to the full SHA. `github.sha`, merge refs, default-branch state and caller HEAD
are not substitutes.

| Job | Required work |
|---|---|
| `python-unit-contract` | Product API unit + Gateway, JUnit, zero unexplained skips, mocked/off network |
| `postgres-full` | PostgreSQL 16, Alembic head, all Product integration tests, migration 0018/0019 roundtrip, zero skips |
| `web-static` | Node 22, `npm ci`, lint and Vitest |
| `release-build` | sole build-once producer: locked Product/Gateway OCI images plus SPA/H2 build/manifest/bundle gate |
| `browser-e2e-visual` | producer H2 artifact + seeded PostgreSQL + real Product HTTP + full Playwright matrix |
| `release-contract` | producer artifacts/images, environment/smoke/nginx/seed/worker-drain/DR/order/rollback tests without rebuild; `deploy/product_api/test_worker_drain.py` is mandatory |
| `qa-required` | exact-SHA aggregator requiring every preceding job and emitting verified SHA + canonical attestation |

Pinned implementation inputs are committed after compatibility verification:

- Python patch and Action commit SHAs;
- hashed `python-bootstrap.lock` for exact pip/setuptools/wheel, hashed
  Product/Gateway runtime locks and a hashed combined test lock;
- exact-patch Python base-image digest used literally by both service
  Dockerfiles;
- Node patch, npm lock and Action SHA;
- Docker BuildKit/buildx tool image/action digest and normalized commit-derived
  source/OCI timestamps;
- PostgreSQL image digest;
- Playwright version/browser revision, matching official container digest and
  normalized font-inventory hash.

Every Python-bearing QA, seed or deploy job uses the same checked-in setup
contract: install bootstrap plus combined test locks with `--require-hashes`,
`--no-deps` and `--only-binary=:all:`, disable build isolation and dependency
resolution for the two local editable test projects, then run `pip check` and
an exact environment/pyproject-to-lock audit. Locks target one declared Linux
x86_64 CPython patch, include no floating requirement or sdist, and record the
isolated resolver identity used to regenerate them. Both PostgreSQL jobs use
the identical digest-pinned PostgreSQL 16 service image.

Release images are a separate audited output of the same lock family. Product
and Gateway each use a service-specific runtime lock (shared packages must have
identical pins/hashes), a literal digest-pinned Python base and a verified
wheelhouse. Local project wheels are built non-editably from the verified SHA;
Docker runs with network disabled and installs only from the wheelhouse with no
resolver/build isolation. The final images are checked with `pip check`, exact
installed-distribution manifests, no-test/no-other-service assertions and
offline API/worker/Gateway smoke. Base, lock, wheelhouse/local-wheel, installed
manifest, OCI digest and release SHA are bound into the release manifest.

`release-build` is the sole producer for Product/Gateway images and SPA/H2
packages. A clean-cache reproducibility check must produce identical installed
manifests and OCI digests before acceptance. Browser/release/deploy consume the
same SHA-named artifacts and cannot rebuild them.

`qa-required` succeeds only after all jobs and emits the verified SHA, exact
artifact names/hashes and `qa-attestation.json` binding job conclusions,
runtime/lock/container digests and release manifests. Deploy refuses any
requested/checked-out/attested/artifact SHA mismatch and consumes these QA
artifacts instead of rebuilding.

No `ubuntu-latest`, floating Python or BuildKit image, unbounded browser channel
or floating database image is an accepted final gate.

The workflow runs `git diff --check`. Repository-wide Python lint/type check
is not claimed because none is configured.

## 23. Disposable PostgreSQL acceptance

The iteration-25 runner owns only loopback/service databases with generated
names and refuses inherited/unknown production targets. It runs:

- complete `services/product_api/tests`;
- migration `0018 -> 0019`, fresh head and legacy-row upgrade;
- allowed downgrade/re-upgrade only when every `projection_scope` and every
  new journal audit field is null and the global decision table is empty;
- downgrade refusal for staged or active non-null scope and for any audited
  transition or global decision binding;
- H1/H2 pin coexistence;
- staged → active noindex/indexable pin append;
- absent/current/stale assignment generation CAS;
- decision idempotency and journal uniqueness;
- concurrent H1/H2 activation/rollback races;
- corrupt/mixed subject/report/pin/artifact rejection;
- sitemap/canonical/Claims H1 → H2 → H1 continuity;
- before/after immutable-row byte/hash equality.

No test may skip due to unavailable DB inside the required CI job.

## 24. Rollback rehearsal

The mandatory rehearsal order is:

1. record exact active assignment and verified H1 rollback pin;
2. activate exact H2 pin through CAS;
3. smoke canonical GET/HEAD, wrong slug, sitemap, assets, browser and Claims;
4. inject one closed failure scenario;
5. CAS back to exact H1 pin before any code rollback;
6. repeat canonical/sitemap/Claims smoke;
7. prove reports, pins, artifacts and assets unchanged;
8. only then rehearse compatible Product/Web/Gateway pointer rollback;
9. keep additive schema; never downgrade migration.

Scenarios include stale CAS, corrupt H2 join, lazy chunk failure, asset pointer
failure and later deploy-phase failure. Each failure has an exact stop/rollback
result and produces no provider/AI call.

## 25. Production runbook decision table

The runbook has explicit `STOP` cells for every unset input:

| Gate | Required evidence | If absent |
|---|---|---|
| release | P1 exact SHA/window/drain timeout, trusted workflow ref, current protection/reviewer evidence and `qa-required` | stop |
| database | P2 backup/restore/current revision/zero unsafe jobs | stop |
| cohort | P3 generation/targets/batch/window | stop |
| monitoring | P4 dashboard/owner/abort policy | stop |
| assets | P5 seeded current+2 and retained compatible image | stop |
| provider | P6 exact disabled/enabled decision | keep disabled |
| AI | P7 exact mode/budgets/model/smoke | fallback-only |
| privacy key | P8 immutable binding/retention | no arbitration activation |
| indexing | P9 exact cohort approval | noindex/no assignment |

Settings are cached, so any approved environment change requires exact process
recreation and verification of the effective redacted configuration. Editing
an env file alone is never evidence of activation.

## 26. Acceptance criteria

Iteration 25 is ready only when:

1. Iteration-24 PostgreSQL prerequisite was closed separately before code.
2. The confirmed iteration-20 presentation contract continuation was merged,
   reconciled and re-tested before iteration-25 code.
3. No previous iteration gap was silently absorbed.
4. H1 bytes/behavior and permanent POST lifecycle remain compatible.
5. New pin/journal migration is additive, preserves old rows and passes real PostgreSQL.
6. H2 activation appends immutable active pins; no staged pin is mutated.
7. Assignment/pin generations are independent and stale CAS is side-effect free.
8. Exact H1 rollback works after active noindex and indexable H2.
9. Sitemap/canonical/robots expose exactly the active assignment and never duplicate H1/H2.
10. DB/API/SSR/embedded/React/chart/Claims parity passes for all profiles.
11. All required widths/interactions/zoom/motion/safe-area/lazy scenarios pass.
12. Visual, accessibility, bundle and post-font zero-shift gates pass in pinned CI.
13. Full Product unit/integration, Gateway, Web and release suites pass with no unexplained skips/new failures.
14. Tests/crawlers/Company Card reads make zero paid/provider/client-telemetry
    calls through the explicitly bounded Claims-navigation request.
15. Privacy scans find no raw identifiers/secrets in public or QA artifacts.
16. Seed/DR/deploy/rollback are rehearsed only on disposable/local state.
17. Production workflow is manual, protected and exact-SHA across all services.
18. Repository runtime defaults remain off/zero.
19. P1–P9 remain explicit and production activation remains unauthorized.
20. `git diff --check` passes and no secret/raw/temp artifact is tracked.
21. Independent end-to-end review returns `VERDICT: READY` with no blocker.

Commit/push still require a separate owner command. Merge and every production
action remain human-controlled after that command.
