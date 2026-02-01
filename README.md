# B2B Chat MVP (RU product + US/EU gateway)

This repo contains two FastAPI services:
- product_api (RU)
- gateway_api (US/EU)

## Local run (Docker)
1. docker compose up --build
2. curl http://localhost:8000/health
3. curl http://localhost:8001/health

Ports:
- 8000: product_api
- 8001: gateway_api
- 5432: postgres

Env examples:
- services/product_api/.env.example
- services/gateway_api/.env.example

## Gateway security (MVP)
- Protect Gateway with IP allowlist on firewall/nginx (only RU IPs).
- All /internal and /v1 endpoints require HMAC signature with timestamp+nonce.
- Set `GATEWAY_SHARED_SECRET` in both services before using any signed endpoints (local tests or prod deploy); generate a strong value for production.

## Product → Gateway contract (MVP)
- Product API calls `POST /v1/chat` on Gateway.
- Headers include `X-Request-ID` and HMAC signature (method+path+timestamp+nonce+body_sha256).
- Body uses shared schemas from `shared/schemas.py`, with `metadata` containing company/user/conversation/message.
- Product sends only the last `CHAT_CONTEXT_LIMIT` completed messages.
- Retries must use the same `message_id` (idempotent) to avoid double-charging.
- Streaming (SSE):
  - Gateway emits `event: delta` with `{text}` and final `event: final` with `{text, usage}`.
  - Product API proxies SSE, buffers final text for saving, and handles disconnects by marking assistant as error.

## OpenAI integration (gateway_api)
- Gateway calls OpenAI Chat Completions API (`/v1/chat/completions`) using `OPENAI_API_KEY`.
- Model is fixed by shared constant `MODEL_GPT_5_2`.
- Gateway normalizes upstream errors as `{"error": {"type","code","message","retryable"}}`.
- Product API stores assistant `text` + `usage` in `messages.usage_json`.

## Rate limiting + content limits (product_api)
- `/v1/chat` лимитируется по company/user/ip (RPM значения в env).
- `/auth/request-link` лимитируется по email+ip (in-memory).
- Ошибки rate-limit и контента возвращаются в формате `{"detail":{"code","message"}}`.
- Максимальный размер текста задаётся `MAX_MESSAGE_CHARS`.

## Observability (minimum)
- X-Request-ID is accepted on Product API and propagated to Gateway.
- Logs redact tokens, secrets, emails, and message content.
- Admin actions write to audit_log for traceability.

## Tests
Product API:
- `cd services/product_api`
- `pip install -e .[test]`
- `pytest`

Gateway API:
- `cd services/gateway_api`
- `pip install -e .[test]`
- `pytest`

Note: Product API tests expect `DATABASE_URL` (or `TEST_DATABASE_URL`) and a running Postgres.

## Production deployment (2 servers)
RU server (product_api):
- `APP_ENV=prod`
- `COOKIE_SECURE=true`
- `COOKIE_SAMESITE=strict`
- `DATABASE_URL`, `GATEWAY_URL`, `GATEWAY_SHARED_SECRET`
- `SESSION_SECRET`, `AUTH_TOKEN_SECRET`, `INVITE_TOKEN_SECRET`
- SMTP vars (`EMAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`)
- Do **not** set `OPENAI_API_KEY` here.

Gateway server:
- `APP_ENV=prod`
- `GATEWAY_SHARED_SECRET` (same value as RU server)
- `OPENAI_API_KEY` (only here)
- `GATEWAY_CLOCK_SKEW_SECONDS`, `GATEWAY_NONCE_TTL_SECONDS`

Nginx:
- Use `deploy/nginx/product_api.conf` on RU server.
- Use `deploy/nginx/gateway_api.conf` on Gateway server.
- Replace allowlist IPs in gateway config with RU server public IPs.

Release order:
- RU: `git pull` → `docker compose build product_api` → `docker compose up -d product_api` → `alembic upgrade head` → `docker compose restart product_api`
- Gateway: `git pull` → `docker compose build gateway_api` → `docker compose up -d gateway_api`

## SMTP requirements (product_api)
Set these env vars before production deploy:
- `EMAIL_FROM` (valid sender address)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- `SMTP_USE_TLS` (true for 587; false for 465 if using implicit TLS via external wrapper)

## Chat API v1 retry behavior
- Client must send `client_message_id` for idempotency.
- If Gateway fails or times out, the client retries with the same `client_message_id`.
- Product API will return the same `user_message_id` + `assistant_message_id` without double-charging.
- Charge is recorded in `ledger` once per user message via `ledger.message_id` unique constraint.
- If company balance is <= 0, `POST /v1/chat` returns `402` with `insufficient credits`.

## Migrations (product_api)
Run from `services/product_api`:
- alembic upgrade head
- alembic revision --autogenerate -m "init"
