# Iteration 25 rollout rehearsal v1

Artifact ID: `company_card_v2_iteration_25_rollout_rehearsal_v1`

Evidence date: `2026-08-28`

Candidate base commit: `31b299ac88b5fac7d5c04082324fb122d63db7e7`

State: `COMPLETE — DISPOSABLE LOCAL REHEARSAL; PRODUCTION STOP`

This is local/disposable rehearsal evidence only. It is not permission to
seed, migrate, deploy, assign, enable provider/AI, change flags or delete a
privacy key in production. P1–P9 remain insufficient or `UNSET/STOP`.

## 1. Rehearsed release controls

- The deploy workflow is manual only, protected by the `production`
  environment and the non-cancelling `prod-deploy` mutex.
- It proves the workflow/ref/repository and requested main ancestry before
  artifact use, requires current canonical P1 evidence, calls reusable
  `qa-required`, downloads rather than rebuilds the exact artifact graph and
  rejects any requested/checked-out/attested/manifest SHA mismatch.
- SSH uses strict reviewed known-host bytes plus an ephemeral agent loaded from
  the protected deploy secret; no floating third-party SSH action is used.
- The SHA-stage compose files reuse the validated
  `com.docker.compose.project` identity of the exact running Product/Gateway
  containers, preventing an accidental second Compose project.
- The worker drain binds its privacy-safe result to a SHA-256 of the exact DB
  URL. Before Alembic, the candidate settings must produce the same digest;
  credentials are never printed or passed in argv.
- H2, Product/workers, Gateway and Web each arm only their own rollback phase.
  Rollback accepts only recorded exact image IDs/pointers; migration is
  additive and never downgraded.
- The final in-process check requires provider, presentation/writer,
  arbitration collection and narrative off; rollout/percentage/budgets/
  concurrency zero; allowlist empty; privacy keys unset; kill switch closed.

Static workflow/order tests are included in the `95 passed` release-tooling
result recorded by the QA evidence file. No SSH or production endpoint was
contacted while running them.

## 2. H2 seed and DR rehearsal

The reviewed seed producer is manual and fixed to exactly three historical
commit/manifest identities. It verifies every manifest and asset byte, emits a
canonical closed checksum graph and uploads a bounded non-production artifact;
it has no SSH/SCP/production step.

`company_public_h2_seed.py verify-bundle` and the seed wrapper were exercised
only against test temp roots. Tests prove:

- exact three-release order and manifest identities;
- checksum closure, file/byte bounds and symlink/non-file rejection;
- explicit absolute empty mode-`0750` root owned by the invoker;
- directory-inode lock, immutable no-overwrite copies and fsync;
- pointer publication last, current + two predecessor selection;
- second fresh-root DR restore equality;
- tampered/extra/collision/failure paths stop without adopting or deleting an
  unknown root.

Normal release/deploy never invokes seed implicitly. Production H2 seed is
still `STOP` pending P5 plus a separate explicit authorization.

## 3. Web release/rollback rehearsal

The Web installer validates a closed tar graph and canonical embedded manifest,
hashes every payload, extracts only beneath a new SHA directory, fsyncs, writes
current + two rollback identities and atomically changes the relative pointer.
The actual producer archive is read-only verified in `release-contract` before
eligibility. Temp-root tests cover GNU-style directory entries, path escape,
link/special/unknown member, digest/payload corruption, unapproved root,
idempotency and injected history/pointer/smoke rollback failures.

No recursive broad-delete primitive exists. A failed switch restores the exact
prior pointer and release-set bytes; an immutable orphan may remain for manual
inspection.

## 4. Worker drain rehearsal

Adapter-only tests use no Docker/DB. The tool captures exactly two distinct
containers/images, validates identical effective drain settings, disables
restart and sends only `SIGTERM`. It starts the deadline before adapter work,
waits for both exact processes, then requires two time-separated equal
privacy-safe aggregate snapshots. Running/leased/active/reserved or unsafe
durable-dispatch state prevents success. Deadline, changing counts, malformed
settings/container/DB output and live-process paths fail without SIGKILL,
Alembic or recreate capability.

The CLI takes DB credentials only from exact worker environment, passes the
connection through `PGDATABASE` rather than argv, and prints only aggregate
counts, DB clock, exact container/image IDs and the one-way DB target digest.

## 5. Disposable release artifact used by local browser rehearsal

The local browser preparation for candidate base
`31b299ac88b5fac7d5c04082324fb122d63db7e7` used:

| Local file | SHA-256 |
|---|---|
| `company-public-h2-31b299ac88b5fac7d5c04082324fb122d63db7e7.tgz` | `a294f0bb921cb46dba50597516cf8b8215843771d0de808fe7fb1458ed56e893` |
| `web-ui-playwright-runtime-31b299ac88b5fac7d5c04082324fb122d63db7e7.tgz` | `cd51c75f8347260d5dd5f67e347d8cef0aa7e2bf7ef9c644fa4e98e29f39a4bb` |
| `release-manifest-31b299ac88b5fac7d5c04082324fb122d63db7e7.json` | `3678b52145aa94d854660ef7f7f9a7b0828f0c079295c8741b9863644637196c` |

The final refreshed H2 archive is `98,390` bytes and contains only the Product
manifest plus its exact five hashed assets. Six sorted checksum rows were
independently recomputed, and the manifest passed the same canonical validator
and exact seven-file root closure used by BrowserE2E. However, its Web and two
OCI records are explicitly
marked `LOCAL DISPOSABLE BROWSER-E2E PLACEHOLDER; UNUSED ARTIFACT`. Therefore
this graph is intentionally non-deployable and cannot be represented as a QA
release or exact-SHA attestation. CI must produce real Web/OCI files and pass
image load/import plus the Web archive verifier before attestation.

## 6. PostgreSQL, migration, CAS and browser rehearsal

The final serialized `PostgresFull` run exited `0` against the exact pinned
PostgreSQL image/platform. Exact `0018` produced JUnit `2/0/0/0` in `9.31s`
(`exact-0018.xml`, SHA-256
`e59bd1d7af50e8d51ba3828aedd9893c28602df1e4f1f3f0c88c7ba08aa5ba70`),
the same database upgraded to exact `0019`, and affected-head produced
`313/0/0/0` in `234.95s` (`affected-head.xml`, SHA-256
`a56bf6aa68d1815e1cb63df0d758073c444e17b4138e4d731b5045c8458b632d`).
Strict JUnit validation and exact-label cleanup were clean.

Review then identified and closed an evidence gap in that affected-head tree:
the H1→H2→H1 node now hashes full nonempty subject-scoped report, pin and
narrative-artifact rows in deterministic primary-key order and proves exact
before/after equality while assignment/journal CAS order grows as required.
The strengthened node is real-PostgreSQL GREEN, `1 passed in 5.30s`, with
cleanup confirmed, and is included in the final affected-head JUnit above.

Browser rehearsal consumed the frozen disposable manifest
`3678b52145aa94d854660ef7f7f9a7b0828f0c079295c8741b9863644637196c`.
Baseline update passed `97/0/0/0` in `7.8m` (JUnit SHA-256
`5c86694e603bc5efc657e5aa0f81e80133cd4f12c432dca32a6bc4d40aea842b`),
then a separate strict comparison passed `97/0/0/0` in `7.8m` (JUnit SHA-256
`9c851296b946a59a922a9d337447de385b2f74d2ed0c7ffb4e7792e9600b6e2f`).
Both lifetimes proved exact-label cleanup. The 28 reviewed baselines have the
defined sorted `name<TAB>lower_sha256<LF>` aggregate SHA-256
`ae6e06947267b0c7cc265a22df3288f02790c06a31ebbecf9e50e296d80609e6`;
all 35 core/lazy cells proved zero post-font shift and all four axe scans had
zero violations.

## 7. Outcome and limitations

The disposable release-tooling, PostgreSQL, H1→H2→H1 CAS and browser rehearsals
are complete and green. No live provider/AI/production action occurred. This
document is not a deploy authorization or QA attestation; P1 remains
insufficient and P2–P9 remain `UNSET/STOP`. No browser timing is promoted to an
SLO until P4 supplies a real owner/window/abort policy.
