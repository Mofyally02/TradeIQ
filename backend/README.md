# TradeIQ API

The API now includes authenticated endpoints and database models for profile/preferences, trading accounts and connection status, trade plans and version history, journal trades/events/reviews/tags, dashboard summaries and analytics, account risk profiles, and TradingView alert receipt/matching. Account records, manually entered trades, plans, reviews, preferences, and alerts persist through SQLAlchemy and Alembic-managed tables.

## Per-user performance intelligence (API foundation)

The authenticated `/api/v1/performance` endpoints compute metrics directly from the
requesting user's closed trades. They do not use a shared dataset, accept a caller-supplied
user ID, or send trade/journal data to an AI provider:

- `GET /api/v1/performance/edge-snapshot` — expectancy in recorded R, profit factor,
  win/loss averages, cumulative-R drawdown/recovery, holding time, recorded MAE/MFE,
  and sample/data-coverage warnings.
- `GET /api/v1/performance/strategies` — per-strategy metrics and a top observed strategy
  only when at least 30 trades have recorded R-multiples.
- `GET /api/v1/performance/setups` — the same analysis grouped by the separately captured
  setup label.
- `GET /api/v1/performance/time` — hour-of-day and weekday outcome cohorts in the selected
  user timezone.
- `GET /api/v1/performance/behavior` — cohorts by explicitly recorded emotion, rule-break
  labels, confluences, user tags, review adherence, and trades opened within a configurable
  interval after a closed loss.
- `GET /api/v1/performance/roadmap` — deterministic review priorities based on the user's
  sample size, R coverage, and recorded rule-break cohorts.
- `POST, GET /api/v1/performance/roadmaps` — save a per-user roadmap snapshot and list prior
  snapshots; `PATCH /api/v1/performance/roadmaps/{roadmap_id}` tracks progress status and notes.

All endpoints support `account_id`, `start_date`, `end_date`, and `timezone` filters.
Dates are inclusive in the selected timezone. An account ID must belong to the signed-in
user. Mixed account currencies suppress combined currency-denominated outputs. MAE/MFE
are only calculated from values actually recorded in R; historical excursion paths cannot
be reconstructed from entry and exit prices alone. Likewise, strategy/behavior cohorts
are descriptive associations, not evidence of cause or financial advice. Older records
remain valid with null excursion and behavior context; manual trade create/update APIs
accept optional setup, stop/target, MAE/MFE, emotion, confluence, and rule-break context.
Position-size leak detection is deliberately not inferred from lot size and stop distance:
contract specifications and verified account equity at entry are required before that
calculation can be made reliably.

Apply the new Alembic migration before using the extended trade context fields in a
deployed database.

The Next.js UI calls the API for authentication, accounts, plans, journal episodes/sections, reviews, timezone preferences, and the MT5/TradingView connection workflows. A Windows MT5 worker logs in with the saved MT5 credentials using the MetaTrader5 Python package and imports history by polling. Dashboard and analytics presentation still derives some values in the browser, and profile/currency/theme settings are not fully surfaced. Object storage, live notification transport, and production PostgreSQL deployment are not configured.

## Requirements

- Python 3.11 or later
- PostgreSQL 14 or later for local application use
- Windows with an installed and logged-in MetaTrader 5 terminal only when using the optional local worker

## Local setup

The recommended local setup uses Homebrew PostgreSQL and the backend startup script. For
first-time setup:

```bash
brew install postgresql@14
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Then, from this directory with the virtual environment activated, start PostgreSQL and
the API with one command:

```bash
bash start-dev.sh
```

The script starts PostgreSQL if needed, creates the local `tradeiq` database if needed,
applies Alembic migrations, and runs the API at `http://localhost:8000`. `/readyz` checks
database connectivity. Stop the API with `Ctrl+C`; stop the database separately with
`brew services stop postgresql@14`.

### Docker Compose alternative

If Docker Desktop is installed, the backend and database can instead run in containers:
```bash
docker compose up --build
```

The Compose database password is for local development only. Do not use it in a deployed
environment. `WEB_ORIGINS` is a JSON list of trusted frontend origins. `COOKIE_SECURE`
must be enabled when `ENVIRONMENT=production`. Interactive API documentation is available
at `http://127.0.0.1:8000/docs`; `/healthz` is a process liveness check.

## Implemented routes

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET, PATCH /api/v1/me`
- `GET, PATCH /api/v1/preferences`
- `GET, POST /api/v1/accounts`
- `GET /api/v1/accounts/{account_id}/connection` (also `/status`)
- `GET /api/v1/accounts/{account_id}/positions` (current open positions)
- `POST /api/v1/accounts/{account_id}/mt5/connect` (save MT5 `login`, `password`, `server`; password is encrypted; returns a one-time worker token)
- `DELETE /api/v1/accounts/{account_id}/mt5/connect` (clear the password and revoke the worker token)
- `GET /api/v1/connectors/mt5/accounts/{account_id}/credentials` (worker only; arguments for `mt5.login()`)

The automated API tests use an isolated in-memory SQLite database. Application development and deployment use PostgreSQL through `DATABASE_URL`; schema creation is performed only by Alembic migrations, not automatically at API startup.

## Connect an MT5 adapter

Add the account in the UI with its MT5 login (account number), password and server name exactly as shown in the terminal. The password is encrypted with a key derived from `CREDENTIAL_ENCRYPTION_KEY` (required in production; a development default is used otherwise). The API returns a one-time bearer token for the worker. Prefer an investor/read-only password.

The `MetaTrader5` Python package runs only on Windows with the terminal installed, so the worker below runs there and talks to the API over HTTPS. A sync is queued when you connect and by **Sync now**.

### Managed Python worker

On a Windows host with the terminal running, install the optional terminal package and set these environment variables in the worker process environment:

- `TRADEIQ_API_URL` — HTTPS base URL of the API
- `TRADEIQ_ACCOUNT_ID` — TradeIQ account UUID
- `TRADEIQ_CONNECTOR_TOKEN` — one-time-provisioned bearer token
- Optional: `MT5_TERMINAL_PATH`, `TRADEIQ_POLL_SECONDS` (default 10), `TRADEIQ_HISTORY_DAYS` (default 365)

The worker reads these from the Windows process environment. For each sync it fetches the saved login, password and server from the API and calls `mt5.login(login, password=..., server=..., timeout=...)`.

The worker initializes the terminal with `mt5.initialize()` (or `MT5_TERMINAL_PATH` when supplied), checks the active account with `mt5.account_info()`, reports failures using `mt5.last_error()`, and closes the terminal connection with `mt5.shutdown()` on exit. These are the connection and login steps described in the [MetaTrader 5 Python `login()` reference](https://www.mql5.com/en/docs/python_metatrader5/mt5login_py), alongside [initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py), [account_info](https://www.mql5.com/en/docs/python_metatrader5/mt5accountinfo_py), [last_error](https://www.mql5.com/en/docs/python_metatrader5/mt5lasterror_py), and [shutdown](https://www.mql5.com/en/docs/python_metatrader5/mt5shutdown_py).

Then run:

```powershell
python -m pip install -e ".[mt5-worker]"
python .\mt5_worker\worker.py
```

The worker polls for explicitly requested syncs, sends account snapshots and broker order/deal/position history, and records processing failures on the sync run. Position-linked deal history is reconciled into journal episodes, including partial and final closes. Run the worker as a restricted service account and use a secret manager or protected service environment for its token.

### MQL5 observation-only EA

The source is [`mt5_connector/MQL5/MofyAllyReadOnlyObserver.mq5`](./mt5_connector/MQL5/MofyAllyReadOnlyObserver.mq5). Open it in MetaEditor, compile it, and attach it to a chart in the intended MT5 terminal. In **Tools → Options → Expert Advisors**, allow WebRequest for the API origin (for example, `https://api.example.com`, without a path). Set the EA inputs:

- `ApiBaseUrl` — HTTPS API origin
- `AccountId` — TradeIQ account UUID
- `ConnectorToken` — one-time account connector token
- Optional: `PollSeconds` (default 10), `HistoryDays` (default 365)

The EA only reads account information, open positions, and bounded order/deal history. It calls the same connector endpoints as the Python worker and does not submit, modify, or close orders. Keep the terminal running and connected; use **Sync now** in TradeIQ to queue a sync for the EA. MT5's WebRequest allow-list must include the API origin.

This adapter currently polls the API for requested syncs and builds a bounded snapshot; it does not maintain a durable local transaction-event queue or run unattended scheduled syncs. History is re-read within the configured window on each request, so keep the window large enough for the episodes that need reconciliation. Neither adapter should treat a terminal disconnect as evidence that a position closed.

## Connect a TradingView alert

While authenticated, call `POST /api/v1/integrations/tradingview/token` to create or rotate the user's token. The response includes the webhook path and the token once; treat the token as a password and rotate it immediately if it is exposed. In the TradingView alert, use that HTTPS webhook URL and include the token in the JSON message body:

```json
{
  "webhook_token": "<one-time token>",
  "alert_id": "{{strategy.order.id}}",
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "price": "{{strategy.order.price}}",
  "lots": "{{strategy.order.contracts}}",
  "timestamp": "{{timenow}}"
}
```

The API stores the alert as a signal owned by the token's user, deduplicates retries by alert ID (or a stable payload hash when no ID is supplied), and never trusts a caller-supplied user ID. It does not infer a filled trade, exit, or profit/loss from a TradingView signal. Review and match alerts to journal trades in the app. Do not include broker passwords, account credentials, or other sensitive data in alert payloads.

## Hosted MT5 sync (MetaApi) — primary flow

Users add an MT5 account with login, password and server. The API provisions a cloud MT5 connection
(`POST /accounts/{id}/metaapi/connect`) and imports balance, open positions and full history in-process,
then re-syncs every `METAAPI_SYNC_INTERVAL_SECONDS`. No per-user worker is needed.

Set once in `backend/.env` and restart the API:

- `METAAPI_TOKEN` — platform token from https://app.metaapi.cloud/token (without it connect returns 503)
- `METAAPI_HISTORY_DAYS` (default 365), `METAAPI_SYNC_INTERVAL_SECONDS` (default 120)
- `CREDENTIAL_ENCRYPTION_KEY` — required in production

The self-hosted Windows `mt5_worker` remains an optional alternative.

## Development goals and experiments
`/api/v1/development/goals` and `/api/v1/development/experiments` (CRUD, per-user). Progress and evidence are computed from the user's own closed trades; see the Version 2.0 PRD.

## Admin Control Center
`/api/v1/admin/*` is a separate, API-authorized operations surface. The admin frontend is
`web/app/admin`. Apply Alembic migrations through `91f2d86c4a10` before using it.

- Persisted roles and permissions are enforced server-side. Legacy `users.role = 'admin'`
  remains a compatibility Super Admin identity; other roles are assigned through the
  audited `/admin/users/{id}/roles` endpoint.
- Admin API access requires TOTP MFA. Sign in with the normal account, then use
  `/admin/mfa/setup` once to obtain a secret for an authenticator app, `/confirm` to
  enable it, and `/verify` for subsequent sessions. The encrypted secret uses the
  existing `CREDENTIAL_ENCRYPTION_KEY` in production. A verified admin session must
  re-verify after 12 hours.
- Repeated invalid codes lock the factor temporarily. Admin access additionally checks
  the target account's current active status; suspending a user revokes existing sessions.
- Administrative writes for settings, roles, user status, incidents and MFA are recorded
  in `admin_audit_logs`. Audit records have no API update/delete operation. Connector
  diagnostics are redacted; broker credentials and journal reflections are excluded.
- `/admin/reconciliation-issues` returns potential unmatched-deal candidates only; it
  does not alter source records or resolve them. `/admin/intelligence/health` reports
  unsupported persisted analysis jobs explicitly rather than inventing queue metrics.
- Account-scoped role grants, recovery codes, dual approval, emergency elevation,
  support-case management, persisted reconciliation workflows, shared taxonomies,
  risk-policy versioning and evaluation datasets are not yet implemented. See the
  Version 2.0 PRD for the release roadmap and security constraints.

## MT5 one-click connector persistence

The generated installers (`app/services/installer.py`, helper `ea/attach_ea.py`) store the TradeIQ EA in the
terminal's saved chart profile and set `[Experts] Account=0`, `Profile=0` in `config/common.ini`. After setup the
trader only opens MT5 and logs in; the EA reloads on every normal launch and keeps running when the account is
switched, and the device connector detects each new login automatically.

## Connection verification bot

Clicking **Connect account** (EA method) opens a verifier that calls
`POST /accounts/{id}/ea/verify` every ~3 s for up to 2 minutes. It checks the connector
install, that MT5 is reporting, that the right login is signed in, and that data is
importing. If MT5 is reporting the account's login but the link is stale, it adopts the
pending detection automatically; otherwise each failed step returns a concrete fix.
