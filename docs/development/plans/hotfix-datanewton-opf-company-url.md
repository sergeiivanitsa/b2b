# Hotfix — Data Newton LLC OPF alias for company URLs

Status: `OWNER_APPROVED`

Date: `2026-09-01`

Branch: `codex/fix-datanewton-opf-company-url`

## Scope

- Add the evidence-backed Data Newton value
  `Общества с ограниченной ответственностью` as an exact provider alias of the
  existing `ООО -> ooo` URL rule.
- Cover the pure URL policy, H1 projection and H2 writer with the observed
  provider value and a sanitized non-production identity.
- Cover the existing writer → worker → PostgreSQL job → H2 pin lifecycle with
  the same observed provider value in the disposable Docker database.
- Preserve default-deny fallback for every unverified OPF value.
- Apply the change only to future, naturally generated publications.

## Explicit exclusions

- No production company lookup, regeneration, republish or URL rewrite.
- No data backfill, migration or mutation of immutable reports and pins.
- No new redirect rule or company-specific behavior.
- No CompanyReport UI, report content, breadcrumbs, Claims or CompanyReport
  Lab changes.
- No additional Data Newton OPF aliases without separate evidence.

## Verification

1. Run focused pure/H1/H2 unit tests.
2. Run the complete Product API unit suite and repository-required Gateway/Web
   checks.
3. Run the complete Product API PostgreSQL suite in the repository's
   disposable Docker environment.
4. Run `git diff --check` and an independent code review.
5. Push the branch and open a pull request only after local checks pass.
