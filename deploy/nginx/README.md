# RU nginx with web_ui static

`deploy/nginx/product_api.conf` is configured for a same-origin setup:

- `/` serves React SPA files from `/opt/b2b/services/web_ui/dist`
- `/api/*` proxies to `product_api` on `127.0.0.1:8000` and strips `/api`
- `/api/v1/chat` has buffering disabled for SSE streaming
- `/api/docs`, `/api/redoc`, `/api/openapi.json` are blocked in production

## Manual rollout on RU server

1. Build frontend in repo root:
   - `npm --prefix services/web_ui ci`
   - `npm --prefix services/web_ui run build`
2. Install nginx config:
   - copy `deploy/nginx/product_api.conf` to nginx site config
   - ensure the configured `root` path exists and contains `index.html`
3. Reload nginx:
   - `nginx -t`
   - `systemctl reload nginx`

## Smoke checks

- `curl -I https://pork.su/` returns `200`
- `curl -i https://pork.su/api/internal/whoami` returns `401` without session
- browser login flow sets cookie and then `/api/internal/whoami` returns `200`
- chat response arrives progressively (not buffered) on `/api/v1/chat`
