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
