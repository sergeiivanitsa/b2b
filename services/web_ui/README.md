# web_ui

React SPA scaffold for the B2B chat UI.

## Local development

```bash
npm install
npm run dev
```

Dev server default URL: `http://localhost:5173`.

## Build

```bash
npm run build
npm run check:company-public-h2-bundle
```

The Company Public H2 bundle check is fail-closed: it verifies the exact Vite
manifest, raw/gzip bytes, eager and finance/arbitration lazy closures, Product
asset-manifest hashes, and absence of Playwright, axe, telemetry and service
worker code from production assets. A positive eager delta needs a reviewed
file-level budget update; the checker does not apply an automatic allowance.

## Company Card v2 browser gate

The iteration-25 Playwright suite never chooses a server or company implicitly.
Its disposable PostgreSQL/Product runner must provide both:

```text
COMPANY_CARD_V2_E2E_BASE_URL=http://127.0.0.1:<runner-owned-port>
COMPANY_CARD_V2_E2E_MANIFEST=<absolute-runner-owned-json-path>
```

The manifest is the strict `company_card_v2_e2e_manifest_v1` contract for the
five sanitized profiles. Missing inputs, a non-loopback origin, an unknown
profile/key, a browser revision mismatch, or an absent preinstalled Chromium
stops the suite. The gate never downloads a browser and must run in the pinned
official Playwright image selected by QA.

The runner exposes Product documents and the already-built H2 release through
one disposable stack process inside the digest-pinned Playwright image. That
process owns both the closed Product relay and the same-origin asset proxy; all
six arguments are mandatory:

```bash
npm run serve:e2e:company-card-v2 -- \
  --browser-port <runner-owned-browser-port> \
  --product-relay-port <runner-owned-relay-port> \
  --product-target-host <127.0.0.1-or-host.docker.internal> \
  --product-target-port <runner-owned-product-port> \
  --asset-root <absolute-release-h2-root> \
  --asset-manifest <absolute-product-h2-manifest>
```

The proxy verifies every declared asset hash and rejects symlinks, unknown
content-addressed assets, non-loopback upstreams and non-GET/HEAD Product
traffic. Its readiness path is `/__company-card-v2-e2e/ready`; it is disposable
test infrastructure and is not registered in Product API.

The stack asserts the pinned image's Node `24.18.1`. Its relay binds only
`127.0.0.1`, rejects arbitrary hosts and URLs, and accepts the Docker gateway
name only when it resolves to one private IPv4 address. The browser container
joins the stack container's network namespace, so its base URL is always the
stack's exact loopback origin. Only the adapter can reach the runner-owned
Product port. Node `22.17.1` remains the release-build and CI-host contract; an
unpinned host Node is never part of BrowserE2E rehearsal or attestation.

```bash
npm run test:e2e:ci
```

Only an explicit visual-review run may update iteration-25 goldens:

```bash
npm run test:e2e:update-snapshots
```

Playwright reports, traces, screenshots and JUnit output are local failure
artifacts under `.tmp/iteration25-playwright`; decision files, database dumps,
secrets and production identifiers are forbidden there.

## Superadmin smoke checklist

1. Sign in as superadmin and open `/superadmin`.
2. Verify Organizations section:
   - loading -> success table
   - filters by name/inn/status
   - status update with row-level save.
3. Verify Admin actions (Organizations):
   - create organization
   - view organization by ID
   - invite organization admin (`404`, `409`, success)
   - add credits (`success`, `409 duplicate idempotency`, retry on network error).

## Production routing smoke

Run:

```bash
curl -i https://pork.su/api/health
curl -i https://pork.su/health
curl -i https://pork.su/api/superadmin/orgs
```

Expected:

- `/api/health` returns JSON and `200`.
- `/health` may return SPA HTML (not API).
- `/api/superadmin/orgs` should be `401/403` without proper superadmin session.
- `404` for `/api/superadmin/orgs` usually means proxy/routing mismatch.

## Regression smoke

- `/login`: request sign-in link.
- `/auth/confirm`: confirm token and redirect.
- `/onboarding/create-org`: create organization for onboarding user.
- `/chat`: send message/stream reply.

## Claims public flow smoke (`/claims/*`)

1. Open `/claims`, submit free-text in step 1.
2. Verify session is stored (`claim_id + edit_token` in `sessionStorage`).
3. On step 2:
   - refresh page and confirm restore from backend (`GET /claims/{id}`),
   - submit guided form with conditional fields,
   - upload at least one file.
4. On step 3:
   - submit contact (`client_email`, optional `client_phone`),
   - trigger preview generation.
5. On step 4:
   - verify preview/paywall rendering,
   - trigger payment stub and verify success state.

State behavior checks:
- `generation_state = insufficient_data`:
  - step 3/4 must redirect back to step 2 with missing fields.
- `generation_state = manual_review_required`:
  - preview and payment remain available.

## Claims admin flow smoke (`/admin/*`)

1. Open `/admin/login` and request magic link.
2. Confirm via `/admin/auth/confirm?token=...`.
3. Open `/admin/claims` and verify list/filters.
4. Open `/admin/claims/:id`:
   - save `final_text`,
   - move status `paid -> in_review`,
   - run send action and verify `sent` result.

Isolation checks:
- Claims admin pages must not depend on legacy `superadmin/*` and `companyAdmin/*` UI flows.
- Claims admin auth uses isolated provider/guard under `/admin/*`.

## Route map (frontend)

Public claims:
- `/claims`
- `/claims/step-2`
- `/claims/step-3`
- `/claims/step-4`

Claims admin:
- `/admin/login`
- `/admin/auth/confirm`
- `/admin/claims`
- `/admin/claims/:id`

Legacy routes remain unchanged and coexist with claims routes.

- claims/web smoke baseline: 2026-03-30
