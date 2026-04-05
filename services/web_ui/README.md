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
```

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
