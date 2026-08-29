# Iteration 25 post-merge main QA v1

Artifact ID: `company_card_v2_iteration_25_post_merge_main_qa_v1`

Evidence date: `2026-08-29`

Final decision: `ACCEPTED — ITERATION 25 MERGE-SHA QA CLOSED`

Production activation: `NOT AUTHORIZED`

## 1. Merge identity

Iteration 25 merged through PR `#153` at
`2026-08-29T10:05:49+10:00`.

| Identity | Exact value |
|---|---|
| PR source commit | `d6f994ebd5d6a259b4c0964b9082b4454c19262d` |
| Protected-main squash commit | `d0860c678754b18959a017580752655dd191fd6c` |
| Parent main commit | `31b299ac88b5fac7d5c04082324fb122d63db7e7` |
| Source/merge tree | `f686bd1a752472c4e3f3295a5c94bf61c22a1bff` |

The source and squash commits have the same tree, but release artifacts and QA
attestations are commit-SHA-bound. The successful PR-head run `33217935892`
therefore did not replace a dedicated verification of the exact merged commit.

## 2. Exact-main-SHA workflow

The manual compatibility wrapper invoked the reusable `qa-required` workflow
for exact release SHA
`d0860c678754b18959a017580752655dd191fd6c` from `main`:

`https://github.com/sergeiivanitsa/b2b/actions/runs/33223251563`

The workflow ran from `2026-08-29T00:20:47Z` through
`2026-08-29T00:32:36Z`, attempt `1`, and concluded `success`.
Slash-separated test tuples below are `tests/failures/errors/skips`.

| Job | Result |
|---|---|
| `resolve-release` | success, `4s` |
| `python-unit-contract` | success, `51s`; Product `1627/0/0/0`, Gateway `31/0/0/0` |
| `postgres-full` | success, `3m29s`; exact-0018 `2/0/0/0`, affected-head `313/0/0/0` |
| `web-static` | success, `52s`; `52` files / `503` tests plus lint/build/static gates |
| `release-build` | success, `2m48s` |
| `browser-e2e-visual` | success, `7m13s`; `97/0/0/0`, cleanup confirmed |
| `release-contract` | success, `1m11s`; `103 passed` |
| `qa-required` | success, `37s` |

The conditional browser **failure** evidence upload was skipped because the
browser job succeeded. No test phase was skipped. Node-action deprecation
annotations were informational and did not change any job conclusion.

PostgreSQL JUnit SHA-256 values were
`4470abb583ece410ed588aaaba1bda06730c48674aab0810f992d079900bf59b`
for exact-0018 and
`f32f693c75cb1203fde796c66dc8cdeef5ac791bd87027ad60064db2ecffb027`
for affected-head. Browser JUnit SHA-256 was
`cb7af8cb38e5fdd0ef986c453ccf85c752d51c0e16d163d1df221eb73991d3b`.

## 3. Canonical artifacts

| Artifact | GitHub ID | Archive SHA-256 |
|---|---:|---|
| `qa-release-d0860c678754b18959a017580752655dd191fd6c` | `9705999703` | `4024e942fa735ca8264f65507e8aaa1e94094f2bc8eebe1ad3e69991ad0cca08` |
| `qa-attestation-d0860c678754b18959a017580752655dd191fd6c` | `9706135886` | `fedfd73f4cb3f2bdd83685621a787162df291e3027ffc9f65cf433cf001a610b` |

The downloaded attestation JSON had SHA-256
`3fcd89c0ac655bfb47fdd8af8c1dea7a542f04ec409afcd00eabb8edffccff4c`.
It declared schema `company_card_v2_qa_attestation_v1`, verified the exact
merged SHA, bound release artifact
`qa-release-d0860c678754b18959a017580752655dd191fd6c`, and recorded every
prerequisite conclusion as `success`. Its release manifest was
`release-manifest-d0860c678754b18959a017580752655dd191fd6c.json` with SHA-256
`595ebe2f3ef60028a62adba8da5ada57442b0e49dbccabbc57559d894060e8e0`.

GitHub records both artifacts as expiring on `2026-09-12`; this tracked file
retains only non-secret identities and digests, not the release payload.

## 4. Protection observation and boundary

At reconciliation time, active repository ruleset `12617222` applied to the
default branch with strict required status `qa-required` from GitHub Actions
integration `15368`. The ruleset required pull requests and resolved review
threads, allowed no bypass actor, and required zero approving reviews. GitHub
reported zero configured environments, so no protected `production`
environment or required-reviewer export existed.

The P1 row in the dated `2026-08-28` planning decision remains a historical
external-state snapshot. Its former `product_api_unit_tests` observation is
superseded by this `2026-08-29` observation; its
`PARTIAL / INSUFFICIENT` conclusion is unchanged.

This observation closes only the post-merge repository QA identity. It is not
the validity-bound P1 production evidence required by the rollout runbook.
Release/window/drain inputs remain unset, P1 remains
`PARTIAL / INSUFFICIENT`, P2–P9 remain `UNSET/STOP`, and no production seed,
deploy, migration, assignment, provider/AI call, positive flag or indexing
change was executed.

## 5. Disposition

Iteration 25 engineering and exact-merge-SHA QA are closed. Company Card v2
remains default-off with H1 as the production-default and rollback path.
Production preparation, default-off deployment, noindex canary, expansion,
indexability and GA each require their separately reviewed decisions and
authorizations.
