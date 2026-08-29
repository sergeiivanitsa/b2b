# RU nginx with web_ui static

`deploy/nginx/product_api.conf` is configured for a same-origin setup:

- `/` serves React SPA files from `/opt/b2b/services/web_ui/dist`
- `/api/*` proxies to `product_api` on `127.0.0.1:8000` and strips `/api`
- `/api/v1/chat` has buffering disabled for SSE streaming
- `/api/docs`, `/api/redoc`, `/api/openapi.json` are blocked in production

## Manual rollout boundary

Do not build on the RU host. The protected exact-SHA workflow consumes the
already checksummed QA Web/H2 artifacts. The SPA root is the atomic pointer
`/var/lib/pork/web-ui/v1/current/site`; a release is installed below
`releases/<40-hex-sha>` only by `deploy/web_ui/install_web_ui_release.sh`.
The installer verifies the archive manifest and every file, switches the
symlink atomically, performs a loopback Host/SNI smoke and restores the prior
pointer/history if that smoke fails.

Validate `product_api.conf` with `nginx -t` before reload. A missing current
pointer or a release not retained by the reviewed rollback set is a STOP. The
complete default-off order and P1–P9 evidence gates are in
`docs/development/runbooks/company-card-v2-rollout.md`.

## Company Card v2 assets

The H2 bundle is separate from the SPA directory.  It is content-addressed and
is installed into `/var/lib/pork/company-public-h2/v1/` before a Product image
can be replaced.  The stable `manifest-set.json` keeps the current release and
two verified predecessors.  The installer never deletes immutable assets; a
new or incomplete host fails until the separately authorized seed/runbook is
performed.  Product rollback therefore chooses only a retained verified
manifest, then rolls Product back.

Initial/DR seed is a separate manual path. The fixed reviewed three-release
bundle is produced by `.github/workflows/company_public_h2_seed_bundle.yml`
without a production connection. `company_public_h2_seed.py verify-bundle`
validates its canonical inventory read-only. The seed wrapper accepts only an
explicit absolute, empty, owned, nonsymlinked root; it copies immutably, fsyncs
and publishes the pointer last. Normal install never invokes seed implicitly.

## Smoke checks

- `curl -I https://pork.su/` returns `200`
- `curl -i https://pork.su/api/internal/whoami` returns `401` without session
- browser login flow sets cookie and then `/api/internal/whoami` returns `200`
- chat response arrives progressively (not buffered) on `/api/v1/chat`
