# Proposed owner decision: iteration 25 planning and activation boundary v1

Artifact ID: `company_card_v2_iteration_25_planning_activation_boundary_v1`

Decision date: `2026-08-27`

Planning-audit base: `886f207d945e35acc1a7e5c07dcff8c36e501bf6`

Implementation base: `NOT ESTABLISHED — exact post-prerequisite origin/main`

State: `PROPOSED — POST-PREREQUISITE REFRESH/REVIEW REQUIRED`

Planning-audit review: `APPROVED 2026-08-27` — planning-base reconciliation,
rollout/CAS and QA/CI scopes only.

Owner implementation approval: `NOT ELIGIBLE / NOT GRANTED`

Production activation: `NOT AUTHORIZED`

## 1. Purpose

This register separates the recommended implementation design from later
production decisions. Approving the iteration-25 specification and plan would
approve D1–D8 for default-off implementation and disposable rehearsal only.
It would not supply any P1–P9 value and would not authorize a production
database read/write, asset seed, deploy, provider/AI call, assignment or flag
change.

## 2. Recommended implementation decisions

### D1 — hard prerequisites remain external to iteration 25

Before the first production-code edit, the exact merged iteration-24
disposable PostgreSQL runner must pass and its debt must be reconciled. The
runner result is not renamed or absorbed as iteration-25 coverage.

The merged base also has a confirmed frozen iteration-20 presentation-create
contract debt: the route accepts query input and does not return the complete
`PresentationLifecycle`. Its exact contract tests and static audit belong to
Stage 0. A separately specified/reviewed iteration-20 continuation must be
merged and reconciled. This base-bound draft then stops: a new clean
implementation branch/worktree must be created from the exact new
`origin/main`, with no automatic rebase/reset or silent draft-branch reuse.
Exact base evidence, the bounded delta audit, Stage 0 and independent plan
review must all be refreshed before any iteration-25 production-code edit.

### D2 — operator-only rollout mutation

H2 pin activation and rollback are available only through an offline Product
API operator CLI using a canonical decision file and explicit digest
confirmation. No public or browser endpoint may mutate assignment. Public
presentation create/status and read routes remain unable to choose a contract,
pin, assignment or rollout bucket through query, header, cookie or body.

The CLI is fail-closed, dry-run first and prints aggregate closed reason codes
by default. It never logs an INN, company name, report UUID, canonical URL,
narrative text, amount, party/case identity, raw decision file or secret.

### D3 — independent assignment CAS

Replace the H1-only helper with a general CAS whose caller supplies:

- one immutable closed command with exact subject/current assignment and
  action-specific source, active and rollback pin identities/digest;
- expected **current assignment generation**;
- canonical decision digest and closed reason/stage code.

Target pin generation and assignment generation are separate values. One
transaction first locks the stable `CompanyReportSubject` row, then loads the
current assignment and decision journal. If the same decision still describes
the current result, replay returns idempotent success even when the original
expected generation is now stale. If a later assignment superseded that
result, replay fails closed as `decision_superseded`. Only a new decision then
validates the expected current assignment generation, validates the complete
target pin lineage, appends the journal record and advances the assignment by
exactly one. The subject lock also serializes the first assignment insert; a
stale generation or different binding fails without mutation.

One decision ID is durably and globally bound to digest/release/action/stage
before any target. An exact NUL-byte-derived, session-level nonblocking
advisory lock serializes that decision. One invocation-owned `NullPool`
physical connection holds the lock and also runs the binding and every ordered
target transaction; PID/lock ownership is checked before each mutation and
reconnect/recheckout is forbidden. Acquisition is explicitly committed, each
guard is the first statement inside a separately connection-owned binding/
target transaction, and no outer/implicit transaction may span targets or the
final unlock. Controlled SIGTERM/cancellation closes target admission and
shielded cleanup explicitly unlocks/closes, with physical driver termination
on uncertain cleanup. Lock loss stops before the next mutation and durable
journal state makes the prefix resumable. Every target uses one lock order—
subject, assignment/journal, ordered pins, report/artifact—and active-pin
append shares the same transaction/context.

Rollback uses the same CAS and an explicitly selected, already validated
immutable H1 pin. It never deletes/rebuilds reports, pins, artifacts or assets
and never downgrades Alembic. An emergency rollback is bound only to the exact
release/tool/auth context, the current assignment, the selected H1 pin and the
CAS precondition; it does not depend on live H2 writer, presentation, cohort,
allowlist or percentage configuration.

### D4 — noindex canary, separate indexability step

The rollout order is:

1. staged H2 test publications, no assignment, `noindex`;
2. exact allowlisted H2 assignments, still `noindex`, only for subjects without
   an indexable H1 canonical publication;
3. controlled sticky-percentage assignments; an indexable H1 subject requires
   an explicitly P9-approved indexable H2 pin and can never be switched to
   noindex H2;
4. separately authorized indexable pin generations and GA.

Resolved staged/noindex H2 pins remain immutable. Indexability is represented
by a newly appended pin generation with exact active scope, canonical path and
last-modified binding; an existing pin is never updated in place. Active
noindex also receives a new pin generation because `projection_scope` and its
projection digest differ from staged bytes. Deindexing by an H1-indexable →
H2-noindex assignment is prohibited rather than authorized by a generic
acknowledgement.

### D5 — Playwright cross-layer gate

Use dev-only `@playwright/test` for a pinned Chromium/Linux real-browser gate
and dev-only `@axe-core/playwright` for repeatable automated accessibility
checks. Reuse assertion semantics from the historical raw-CDP evidence without
rewriting that harness. The production bundle graph must prove that neither
test dependency is reachable. The browser job runs in a digest-pinned official
Playwright container whose tag matches the exact npm package/browser revision;
it performs no mutable OS/browser install and verifies a committed normalized
font-inventory hash. Both PostgreSQL consumers use the same digest-pinned
service image.

Every Python-bearing CI job consumes checked-in `--require-hashes` bootstrap
and full test locks for one exact Python patch/platform. Build isolation and
dependency resolution are disabled after the locked wheels are installed;
editable local packages are installed `--no-deps`, followed by `pip check` and
an exact environment audit. Product and Gateway release images use literal
digest-pinned Python bases and separate hashed runtime-lock wheelhouses. Their
Docker builds have no network or resolver, install non-editable local wheels,
and are audited/smoked before their image digests enter QA attestation.

### D6 — sanitized acceptance profiles

The tracked `СКС` acceptance profile is only an anonymized, synthetic
`sks_morphology_complete_v1` fixture: all names, identifiers, URLs, dates and
provider material are replaced; no production raw or secret is committed.

A real СКС company, if later chosen as a production canary, is an external
owner-approved target. Its identifier and output do not enter git or CI
artifacts.

### D7 — manual exact-SHA production workflow

Merge no longer triggers production deployment. Deployment becomes an
explicit manual workflow against one immutable 40-hex commit, protected by the
production environment and the complete QA workflow for that same SHA.

The dispatcher itself must be the workflow at the fetched protected-main head;
a branch/fork/older workflow ref is rejected. YAML cannot prove repository or
environment protection, so deploy also requires external P1 evidence that
protected main requires `qa-required` and that the production environment has
the intended required reviewers. Missing/stale evidence is STOP.

Reusable QA has one validated `release_sha` value. Every checkout, cache,
artifact and job result is bound to it; the aggregator emits a canonical
attestation and verified SHA. One QA producer builds the locked Product/Gateway
OCI images and SPA/H2 packages exactly once; browser/release/deploy only consume
those checksummed artifacts. Deploy refuses any requested/checked-out/attested
SHA or artifact mismatch.

RU Product/worker, US Gateway, SPA and H2 asset release all use that exact SHA.
Workers must drain/stop successfully; SPA switching is atomic and retains a
previous release. A later-phase failure restores the recorded compatible code
and pointers without schema downgrade.

Drain means `SIGTERM` without forced-kill escalation, both old worker processes
exited, and stable aggregate DB predicates proving zero report/narrative/outbox
leases, zero reserved credit and terminal handling of every durable AI dispatch
marker. P1 supplies the checked deadline; any ambiguous state stops before
Alembic.

### D8 — deterministic, base-relative performance gate

Iteration 25 does not invent a business latency/SLO number. CI instead enforces:

- no external browser request and no eager request for lazy chart chunks;
- zero deterministic layout-shift contribution after fonts are ready through
  hydration and lazy-chart completion for the acceptance profiles;
- an exact committed raw/gzip asset baseline measured in the pinned CI
  environment; any positive eager-closure delta requires an explicit reviewed
  budget update with file-level attribution;
- a post-font zero-shift gate that holds the entry module, proves the SSR
  marker, awaits fonts, proves Layout Shift observer support, arms the observer,
  records a monotonic cutoff, releases the entry and awaits explicit hydration
  plus lazy terminal state; buffered entries before the cutoff are diagnostic,
  then stable frames and `takeRecords()` drain the observer before assertion;
  every positive post-cutoff entry fails regardless of `hadRecentInput`;
- LCP and request timing are recorded as diagnostic artifacts, not promoted to
  production SLOs without P4.

## 3. Production decisions deliberately left pending

| ID | Required owner input | Current state |
|---|---|---|
| P1 | exact release commit/window/drain timeout; trusted workflow-ref proof; current protected-main required-status and production required-reviewer evidence | `UNSET` |
| P2 | DB backup/restore evidence, migration preflight and execution approval | `UNSET` |
| P3 | rollout generation, allowlist, percentage ladder, batch cap and observation windows | `UNSET` |
| P4 | health/error/latency SLOs, abort thresholds and monitoring owner | `UNSET` |
| P5 | initial/DR H2 asset seed authority and three retained manifests/images | `UNSET` |
| P6 | DataNewton operation mode and any live provider smoke | `DISABLED / UNSET` |
| P7 | AI model, daily/monthly credits, concurrency, monetary ceiling and paid smoke | `DISABLED / UNSET` |
| P8 | immutable key-version binding plus zero-live-reference deletion proof; reads use stored masked facts/nonsecret tombstone only | `UNSET` |
| P9 | indexable cohort/GA approval | `UNSET` |

Every production command must cite the exact decision IDs it consumes. An
unset or mismatched input is a stop condition, not a value to infer from tests,
repository defaults or a previous rollout.

## 4. Authorization ladder

```text
planning approval
  -> reviewed specification and plan
  -> owner implementation approval
  -> default-off implementation + disposable QA
  -> independent end-to-end VERDICT: READY
  -> separate commit/push command
  -> human merge
  -> separately approved production preflight/seed/deploy
  -> separately approved noindex canary assignment
  -> separately approved expansion/indexability/GA
```

Passing an earlier step never authorizes a later one.
