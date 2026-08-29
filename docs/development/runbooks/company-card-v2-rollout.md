# Company Card v2: QA, default-off deploy, rollout and rollback

Status: **production activation is not authorized**. This runbook records the
fail-closed procedure implemented in iteration 25. It is not evidence that any
production command, migration, seed, assignment, provider call or AI call was
executed.

## Authorization matrix

Every production value starts and remains `UNSET/STOP`. Repository defaults
remain provider off, narrative off/kill-switched with zero budgets, rollout
generation `0`, percentage `0`, empty allowlist and no indexable assignment.

| Gate | Required separately reviewed evidence | Current value | Missing/invalid result |
|---|---|---|---|
| P1 release | exact main-history SHA, deployment window, drain bounds, current protected-main `qa-required` export and current `production` reviewer export | `UNSET/STOP` | stop before QA/artifact download |
| P2 database | backup identity, tested restore, exact current revision, aggregate zero unsafe jobs/leases/reservations | `UNSET/STOP` | stop before worker signal/Alembic |
| P3 cohort | generation, sanitized targets, batch/window and decision digest | `UNSET/STOP` | no assignment |
| P4 monitoring | dashboard, owner, observation window and abort policy | `UNSET/STOP` | no activation |
| P5 assets | verified current + two predecessors and matching compatible images/Web releases | `UNSET/STOP` | no seed/deploy |
| P6 provider | explicit disabled/enabled decision | `UNSET/STOP` | keep disabled |
| P7 AI | mode, model, budgets, concurrency and paid-smoke authorization | `UNSET/STOP` | fallback-only, kill switch closed, all budgets zero |
| P8 privacy key | immutable key binding, retention/deletion proof and tombstone plan | `UNSET/STOP` | no arbitration activation or deletion |
| P9 indexing | exact cohort/canonical/sitemap approval | `UNSET/STOP` | noindex and no assignment |

Never replace a missing value with an example threshold, host, company, secret
or positive budget. A repository check cannot infer GitHub branch/environment
protection; P1 must contain a current canonical external export with a validity
interval and digest.

## Exact release and QA contract

1. Select one exact lowercase 40-hex commit already reachable from protected
   `main`. A PR run always uses its head SHA, never the merge ref.
2. `.github/workflows/qa.yml` checks out that SHA in every job. The only image/
   Web producer is `release-build`; all artifacts, checksums, manifests, JUnit
   results and the final attestation contain the full SHA.
3. The required protection status is the single `qa-required` job. Cancelled,
   skipped or failed prerequisites fail the aggregator.
4. Product/Gateway wheels and dependency wheelhouses use the checked-in hash
   locks. Release Docker builds have networking disabled and runtime installs
   use `--no-index`, `--no-deps` and `--require-hashes`.
5. Deploy consumes the exact QA OCI/Web/H2 artifacts and attestation. It never
   rebuilds a caller checkout or default branch.

The former Product-only workflow is a manual compatibility wrapper and is not
a competing required status.

## Read-only preflight (P1/P2/P5)

Before any remote write, confirm the workflow itself is the file at the current
protected-main head, the repository is the protected repository (not a fork),
and the requested release is an ancestor of that head. Validate P1 external
evidence before QA or artifact download. Its canonical signed-off payload must
bind the exact release SHA, current protection observation/expiry, deployment
window and both submitted drain bounds; a mismatch or a run outside either
validity interval is `STOP`.

The separately authorized RU/US preflight must then record, without printing
secrets or row identifiers:

- exact current Product/report-worker/narrative-worker/Gateway container and
  image identities;
- exact H2 `manifest-set.json` digest and Web `current`/`release-set.json`;
- schema revision and backup/restore evidence identity;
- aggregate report/outbox/narrative/runtime/reservation counts and DB clock;
- redacted effective settings, including every default-off/zero value;
- enough disk space and exact approved stable roots.

Any unexpected process count, unretained pointer, non-additive migration,
unknown database, inherited credential, nonzero unsafe aggregate or missing
compatible predecessor is `STOP`. Do not repair, delete or adopt an unknown
resource inside the deploy run.

## Initial H2 seed and DR rehearsal

The seed set is frozen oldest to newest:

| Commit | Product H2 manifest SHA-256 |
|---|---|
| `cfbd37c02c99c569e47806337ed0306c9a722551` | `e48fa51389f5365f9fe445b0c49a0a2224103502a6b742ca1cb9bd705f63a6d6` |
| `867c0d21558dc8e73a0e55a42167b38ced6d6b67` | `506b92be298a1e81d8550dad08c5ce4b5ece8fa3d163a78d286642ec75b4b060` |
| `e7478a2fba9aaca17829c3d99e89e8d83d4b3188` | `97a76daefbb73e1b78935916516fa093f3db5027e09ea44f52df6f63ac18222b` |

Run the manual `Company Public H2 reviewed seed bundle` workflow only to build
the bounded non-secret bundle; it never connects to production. Reverify the
artifact checksum, extract into a newly created disposable directory, and run
the read-only parser before any seed:

```powershell
python deploy/nginx/company_public_h2_seed.py verify-bundle C:\ABS\seed-bundle\seed-inventory.json
```

For a disposable Linux rehearsal, create one new empty mode-`0750` owned root,
then invoke the wrapper with absolute paths:

```bash
bash deploy/nginx/seed_company_public_h2_assets.sh \
  /ABS/seed-bundle/seed-inventory.json /ABS/disposable-empty-root
python3 deploy/nginx/company_public_h2_seed.py verify \
  /ABS/disposable-empty-root /ABS/disposable-empty-root
python3 deploy/nginx/company_public_h2_seed.py select \
  /ABS/disposable-empty-root /ABS/disposable-empty-root MANIFEST_SHA256
```

The root must be explicit, empty, nonsymlinked and owned by the invoker. Seed
publishes its pointer last and never deletes/overwrites a collision. A DR
rehearsal restores into another fresh temp root and compares all three selected
manifests/assets. Production `/var/lib/pork/company-public-h2/v1` seed remains
`STOP` until P5 and a separate production authorization exist.

## Manual default-off deploy

`.github/workflows/deploy_prod.yml` is `workflow_dispatch` only, uses the
protected `production` environment and serializes the whole operation with
`prod-deploy` / `cancel-in-progress: false`. All P1–P9 evidence digests and
P1-approved drain values are required inputs with no repository defaults.

The fixed order is:

1. reverify QA attestation, release manifest and every artifact checksum;
2. perform read-only RU/US preflight and record compatible prior identities;
3. install and loopback-verify H2 assets;
4. drain the exact report and narrative workers using `SIGTERM` only;
5. run additive `alembic upgrade head` against the explicit P2 database;
6. recreate Product and both workers from the exact SHA image and verify health;
7. recreate Gateway from the same exact SHA and verify image identity;
8. install the SHA-bound Web archive under
   `/var/lib/pork/web-ui/v1/releases/<sha>`, atomically switch `current`, reload
   nginx and smoke public/API/auth boundaries;
9. verify redacted effective config still has provider/narrative/rollout/
   indexing controls off/zero and no assignment was made.

Candidate compose files live in a SHA staging directory, but they must not
create a second compose project. Preflight records the exact
`com.docker.compose.project` labels of the running Product and Gateway
containers; replacement, verification and rollback all pass those validated
project names explicitly.

The drain deadline is not invented here. `deploy/product_api/worker_drain.py`
rejects a deadline shorter than the configured worker shutdown grace and
provider/Gateway timeout bounds. It disables restart, sends only `SIGTERM`,
waits for both captured processes, and requires two stable privacy-safe zero-
unsafe snapshots. It never runs Alembic/recreate and never escalates to
`SIGKILL`. Failure stops before migration.

Settings are cached. Editing an env file is not activation evidence; an
authorized setting change requires exact process recreation followed by a
redacted in-process check. Do not print env files, URLs with credentials,
identifiers, decision contents or row-level lifecycle data.

## Staging and activation (still unauthorized)

Only after P1–P8 are separately approved may an offline decision file be
created, canonicalized, hashed, stored and dry-run against sanitized targets.
Precreate H2 pins as staged/noindex/non-sitemap and verify canonical/report/
Claims parity without provider or AI calls. Staging does not change selection.

Allowlist, percentage and indexable activation are distinct later decisions.
They require P3/P4/P9, the exact release/config/decision identity, CAS from the
observed prior assignment, bounded batches and an abort policy. Deploy itself
must never set a positive flag, budget, percentage, allowlist or assignment.

## Observation, abort and rollback

P4 supplies real dashboard queries, owner, window and thresholds; until then
only diagnostics are recorded and no production SLO is claimed. Operational
queries expose aggregate counts only.

On rollout abort, first CAS the affected assignment from H2 to its exact
retained H1 predecessor. Keep noindex until P9 explicitly authorizes indexing.
Verify canonical/sitemap/Claims parity, zero read-side writes, zero provider/AI
calls and retained masked-fact verification.

On a later deploy-phase failure, the workflow restores the recorded compatible
Product/Gateway images plus H2/Web/nginx pointers where safe and re-smokes them.
Migration `0019` is additive and is never downgraded. A missing/changed rollback
identity is `STOP`, not permission to rebuild or select another release.

P8 secret deletion is a separate irreversible decision. It requires zero
nonterminal jobs/leases/retries/outbox/reservations, verification that every
terminal masked projection reads without secret bytes, and an immutable key-ID/
KMS-version tombstone. Any retained-read dependency on secret bytes is `STOP`.

## Repository-only verification

These commands use disposable/local state and do not authorize production:

```powershell
python scripts/check-python-ci-lock.py
python -m pytest deploy/nginx deploy/product_api deploy/web_ui -q -ra -p no:cacheprovider
pwsh -File deploy/nginx/test_product_api_conf.ps1
pwsh -NoProfile -File scripts/run-iteration25-postgres-tests.ps1 -Mode PostgresFull
git diff --check
```

Browser acceptance additionally consumes the already built SHA-bound H2 and
Playwright-runtime artifacts. The runner owns PostgreSQL, seeded Product,
same-origin proxy, loopback URLs, absolute profile manifest, pinned Playwright
container and cleanup; it accepts no public/default base URL.
