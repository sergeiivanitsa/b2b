# Company Card v2: QA, default-off deploy, rollout and rollback

Status: **iteration 25 production recovery is under review**. The historical
default-off QA merge did not upgrade the legacy production server and did not
make Company Card v2 available there. This runbook now separates the one-time
`0015` bootstrap from the later single-company canary. It is not evidence that
either operation has been executed.

## Concrete production inputs

Do not use abstract gate labels as substitutes for these inputs. Every row must
be bound to the exact production operation; a missing or mismatched row stops
before mutation.

| Input | Required value | Current repository/live fact | Missing/invalid result |
|---|---|---|---|
| Release | exact post-merge commit in protected `main`, wholly successful exact-SHA QA and approved maintenance window | no recovery merge exists yet | stop before artifact download |
| Legacy state | schema `0015_claims_company_report_handoff`, exact legacy image `6bee95e...`, one Product and one report worker, no narrative worker, legacy nginx/Web and uninitialized H2/Web stores | confirmed read-only on 2026-08-29 | any difference stops the one-time workflow |
| Database recovery | fixed external recovery hook plus immutable backup/PITR identity and SHA; after ingress and both writers stop, `verify-current-frozen` must prove coverage through the final write; restore rehearsal must return exact `0015` | external input still required | stop before `migration-armed` and Alembic |
| H2 assets | reviewed three-release seed workflow run and archive SHA plus the exact candidate QA artifact | fixed manifests are in this runbook; run/SHA still required | stop before installing nginx bridge |
| Access | protected GitHub `production` environment, required reviewer, SSH key and pinned known-host identity | external input still required | workflow cannot start |
| Canary | allowlist exactly `7707079463`, percentage `0`, a positive new generation, explicit observation seconds and abort reference | target approved; live generation/observation values still required | no H2 job or assignment |
| Arbitration key | retained active key ID and keyring outside git, bound to the canary plan | external input still required | no arbitration-enabled H2 |
| Presentation | current authorization stops at staged fallback H2; H1 rollback pins are always indexable | a separate owner authorization is required for indexable H2 activation | fail closed; no assignment |

Never replace a missing value with an example threshold, host, company, secret
or positive budget. Repository tests cannot prove branch/environment
protection, a restorable production backup or a retained production key.

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

## Read-only preflight

Before any remote write, confirm the workflow itself is the file at the current
protected-main head, the repository is the protected repository (not a fork),
and the requested release is an ancestor of that head.

For the normal post-bootstrap `deploy_prod.yml` path only, validate its external
release evidence before QA or artifact download. That canonical signed-off
payload binds the exact release SHA, current protection observation/expiry,
deployment window and both submitted drain bounds; a mismatch or a run outside
either validity interval is `STOP`. The one-time legacy-0015 bootstrap does not
claim or consume this normal-deploy payload. It instead fails closed on its own
exact protected-main workflow/SHA, sole legacy revision and container topology,
immutable legacy image/config/nginx/Web identities, QA and three-release seed
artifacts, and external backup/recovery-hook identities described below.

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

For a disposable Linux rehearsal, create a new canonical parent and one empty
root, both owned by the current effective user with exact mode `0750`, then
invoke the wrapper with absolute paths:

```bash
install -d -m 0750 /ABS/disposable-h2-rehearsal
install -d -m 0750 /ABS/disposable-h2-rehearsal/empty-root
test "$(realpath -e -- /ABS/disposable-h2-rehearsal)" = /ABS/disposable-h2-rehearsal
test "$(stat -c '%u:%a' -- /ABS/disposable-h2-rehearsal)" = "$(id -u):750"
test "$(stat -c '%u:%a' -- /ABS/disposable-h2-rehearsal/empty-root)" = "$(id -u):750"
bash deploy/nginx/seed_company_public_h2_assets.sh \
  /ABS/seed-bundle/seed-inventory.json /ABS/disposable-h2-rehearsal/empty-root
python3 deploy/nginx/company_public_h2_seed.py verify \
  /ABS/disposable-h2-rehearsal/empty-root /ABS/disposable-h2-rehearsal/empty-root
python3 deploy/nginx/company_public_h2_seed.py select \
  /ABS/disposable-h2-rehearsal/empty-root /ABS/disposable-h2-rehearsal/empty-root MANIFEST_SHA256
```

The parent and root must be explicit, canonical, nonsymlinked and owned by the
invoker; the root must be empty. Seed
publishes its pointer last and never deletes/overwrites a collision. A DR
rehearsal restores into another fresh temp root and compares all three selected
manifests/assets. Production `/var/lib/pork/company-public-h2/v1` seed remains
forbidden until the exact seed run/SHA and production workflow review exist.

Production binds both immutable asset stores to the exact running nginx worker
identity `www-data:www-data`: roots/directories are `root:www-data` `0750` and
files are `root:www-data` `0640`. Bootstrap creates a missing `/var/lib/pork`
chain under that effective group. Bootstrap and every later normal install or
pointer rollback run with root uid plus the verified nginx gid, then prove the
worker identity can traverse/read the complete published trees before success.

## One-time bootstrap from legacy `0015`

Use `.github/workflows/deploy_prod_legacy_0015_bootstrap.yml` exactly once,
only from its merged protected-main version. It accepts the exact candidate
SHA, the only authorized legacy SHA, the reviewed seed run/SHA, the external
backup/PITR identity/SHA, the fixed recovery-hook SHA and bounded drain values.

Do not use `alembic downgrade` as the recovery rehearsal. On a disposable
production-shaped copy, prove that `0015 -> head` preserves the legacy cohort
and that a lossy downgrade is refused atomically with head, schema and migrated
state unchanged. Separately restore the exact pre-migration backup into a fresh
disposable database, verify sole `0015`, and re-upgrade that restored database
to head. Retain this restore/re-upgrade evidence under the exact backup
artifact identity/SHA and recovery-hook SHA supplied to the bootstrap.

The workflow stops unless production has the exact legacy shape listed above.
Its mutation order is deliberate:

1. verify the candidate QA attestation and both candidate/seed archives;
2. re-check `0015`, exact legacy containers, nginx and uninitialized stores;
3. install a maintenance bridge: Product-backed routes return `503`, while
   only immutable H2 assets and the candidate Web pointer can be served;
4. stop legacy Product with `SIGTERM`, then drain exactly one report worker;
5. call the fixed external hook as `verify-current-frozen`; it must prove the
   immutable backup/PITR set covers the final database write after both writers
   stopped;
6. validate the candidate settings offline, preserving the existing DataNewton
   state while every H2/narrative/rollout control is off/zero;
7. arm migration, run `0015 -> head`, start exact candidate Product/report/
   narrative workers and verify their image identities and health;
8. initialize the first versioned Web pointer, switch regular nginx and repeat
   the in-process default-off/provider-preservation check.

Any failure after migration is armed stops candidate services, calls external
`restore`, proves `verify-restored` at exact `0015`, and only then recreates the
exact legacy Product/report pair. Narrative is removed, legacy nginx is
restored and the first Web pointer is transactionally returned to the
uninitialized state. An image-only rollback after `0016` is forbidden.

Do not run the workflow if the recovery hook cannot prove current-frozen
coverage or if the restore rehearsal has not already returned exact `0015`.

## Normal post-bootstrap default-off deploy

`.github/workflows/deploy_prod.yml` is `workflow_dispatch` only, uses the
protected `production` environment and serializes the whole operation with
`prod-deploy` / `cancel-in-progress: false`. It remains strict and is usable
only after the one-time bootstrap established the versioned H2/Web stores and
both current workers. Required evidence digests and approved drain values have
no repository defaults.

The fixed order is:

1. reverify QA attestation, release manifest and every artifact checksum;
2. perform read-only RU/US preflight and record compatible prior identities;
3. install and loopback-verify H2 assets;
4. drain the exact report and narrative workers using `SIGTERM` only;
5. run additive `alembic upgrade head` against the exact reviewed database;
6. recreate Product and both workers from the exact SHA image and verify health;
7. recreate Gateway from the same exact SHA and verify image identity;
8. install the SHA-bound Web archive under
   `/var/lib/pork/web-ui/v1/releases/<sha>`, atomically switch `current`, reload
   nginx and smoke public/API/auth boundaries;
9. verify redacted effective config preserves the prior DataNewton state, keeps
   H2/narrative/rollout/indexing controls off/zero and makes no assignment.

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

## Exact canary for `7707079463`

This is a single-target operation, not a percentage rollout. Before running it,
configure a positive new generation, allowlist containing only the approved
target, percentage `0`, arbitration collection plus the retained mask key, and
temporarily open presentations/writer. DataNewton must retain its existing
enabled state and API key. Keep AI narrative disabled, kill-switched and at
zero budgets/concurrency; the narrative worker finalizes deterministic
fallback without a paid call.

Create absolute nonsymlinked private target, plan and receipt paths, owned by
the operator and mode `0600` for files (the receipt path must not exist yet).
Do not print them. Run inside the exact candidate Product image/runtime:

```bash
python -m product_api.company_reports.company_card_v2.canary inspect \
  --target-file /ABS/private/canary-target.txt \
  --plan-file /ABS/private/canary-plan.json

python -m product_api.company_reports.company_card_v2.canary prepare \
  --plan-file /ABS/private/canary-plan.json \
  --confirm-digest PLAN_DIGEST \
  --receipt-file /ABS/private/canary-receipt.json
```

`inspect` is read-only. `prepare` repeats the exact release/schema/config/CAS
checks, reuses or creates one immutable eligible H1 rollback pin without a
publication or assignment, and enqueues at most one exact arbitration-enabled
V3 H2 job. Before committing that transaction it exclusively writes and fsyncs
the canonical receipt plus its parent directory. The receipt binds the plan
digest and exact subject/head generation/presentation/report/job tuple. It
never calls a provider itself. An unsuitable H1 report, changed
assignment/head, already active H2 assignment, stale plan or unwritable receipt
produces zero canary mutation.

Never reconstruct a missing receipt from the current head. A stale receipt or
an uncertain commit is `STOP`: preserve it for forensic comparison, verify the
exact DB lineage and commit outcome, and do not delete or overwrite it. A retry
is allowed only after exact DB verification proves that the earlier transaction
did not commit; it then requires a separately reviewed fresh inspect and a new
private receipt path. If commit occurred or the outcome remains uncertain,
remain stopped and never enqueue a replacement H2 job.

Immediately close presentations/writer in the public Product configuration and
recreate Product only. The already-running report worker retains the approved
job configuration until it finishes; the narrative worker resolves fallback.
The read-only commands intentionally remain usable with the public gates closed:

```bash
python -m product_api.company_reports.company_card_v2.canary status \
  --plan-file /ABS/private/canary-plan.json \
  --receipt-file /ABS/private/canary-receipt.json
```

The currently authorized recovery ends here after status reports a complete,
resolved deterministic fallback. Do not assign H2. In particular, do not run
`build-decisions` with `false`: the CLI rejects it because every retained H1
rollback pin is structurally indexable, so that pair would change indexing on
rollback.

Only after the owner separately authorizes an indexable one-company canary and
provides its concrete authorization reference, continue:

```bash
python -m product_api.company_reports.company_card_v2.canary build-decisions \
  --plan-file /ABS/private/canary-plan.json \
  --receipt-file /ABS/private/canary-receipt.json \
  --authorization-reference AUTH_REFERENCE \
  --abort-policy-reference ABORT_REFERENCE \
  --observation-window-seconds APPROVED_SECONDS \
  --h2-indexable true \
  --activate-decision-id DISTINCT_UUID \
  --rollback-decision-id OTHER_DISTINCT_UUID \
  --output-dir /ABS/private/canary-decisions
```

Wait for a `complete` H2 and resolved staged fallback before building the
indexable decisions, then recreate workers with the public gates closed. A
`partial` report or paid/artifact narrative is not eligible. The command
exclusively creates canonical private activation and emergency-rollback files
and refuses to overwrite them. Validate and dry-run both files with the
existing rollout CLI before the only mutation:

```bash
python -m product_api.company_reports.company_card_v2.rollout validate --decision-file /ABS/private/canary-decisions/company-card-v2-canary-activate.json
python -m product_api.company_reports.company_card_v2.rollout plan --decision-file /ABS/private/canary-decisions/company-card-v2-canary-activate.json
python -m product_api.company_reports.company_card_v2.rollout validate --decision-file /ABS/private/canary-decisions/company-card-v2-canary-rollback.json
python -m product_api.company_reports.company_card_v2.rollout plan --decision-file /ABS/private/canary-decisions/company-card-v2-canary-rollback.json
python -m product_api.company_reports.company_card_v2.rollout apply --decision-file /ABS/private/canary-decisions/company-card-v2-canary-activate.json --confirm-digest ACTIVATE_DIGEST
python -m product_api.company_reports.company_card_v2.rollout status --decision-file /ABS/private/canary-decisions/company-card-v2-canary-activate.json
```

Noindex activation is always rejected by this exact recovery CLI because the
audited emergency H1 target is indexable. Never weaken or bypass this check.
Deploy itself never sets a positive generation, allowlist, budget or
assignment.

## Observation, abort and rollback

The decision file supplies the real observation window, responsible operator
and abort reference; until those are fixed, activation does not run.
Operational queries expose aggregate counts only.

On rollout abort, first CAS the affected assignment from indexable H2 to its
exact retained indexable H1 predecessor. Thus rollback preserves, rather than
changes, the explicitly authorized indexing state.
Verify canonical/sitemap/Claims parity, zero read-side writes, zero provider/AI
calls and retained masked-fact verification.

Execute the already validated emergency decision with its own digest:

```bash
python -m product_api.company_reports.company_card_v2.rollout rollback --decision-file /ABS/private/canary-decisions/company-card-v2-canary-rollback.json --confirm-digest ROLLBACK_DIGEST
```

On a later deploy-phase failure, the workflow restores the recorded compatible
Product/Gateway images plus H2/Web/nginx pointers where safe and re-smokes them.
Migration `0019` is additive and is never downgraded. A missing/changed rollback
identity is `STOP`, not permission to rebuild or select another release.

Mask-key deletion is a separate irreversible decision. It requires zero
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
