# TradeIQ Backend, Database, and Frontend Integration Blueprint

## Purpose and current status

This document describes how to connect the TradeIQ interface to a persistent backend so that user inputs, imported execution records, and derived analytics share one reliable source of truth.

The app in `web/` uses the FastAPI backend for authentication, accounts, trade plans, journal episodes/sections, reviews, timezone preference, and MT5/TradingView credential workflows. API-loaded records are the browser UI's working data; the legacy `localStorage` workspace is left untouched. CSV import posts records to the API. Some dashboard/analytics presentation still calculates in the browser instead of consuming all server analytics routes; profile/currency/theme settings, evidence uploads, alert review, risk controls, and live push updates remain unfinished. The backend uses PostgreSQL models/migrations and includes a Windows MT5 polling worker and authenticated/idempotent import endpoints, but the worker has not been validated against a live terminal. Object storage and production deployment are not configured.

## 1. Recommended architecture

Use one PostgreSQL database with related tables for the application's different kinds of data. Do not create a separate physical database for every feature or data point: the journal needs to relate plans, accounts, execution facts, reviews, and analytics.

```text
Next.js frontend (web/)
  Forms, tables, dashboards, charts, loading/error states
                 │ HTTPS API requests
                 ▼
FastAPI backend
  Authentication, validation, permissions, services, API responses
      │                         │
      ▼                         ▼
PostgreSQL                 Private object storage
Structured records         Screenshots and attachments
      ▲
      │ authenticated internal connector/worker
MT5 integration and import jobs
```

Recommended responsibilities:

- **Frontend — Next.js + TypeScript:** display server data, collect user input, provide responsive interaction, and show clear loading, empty, success, and error states. It must not connect directly to PostgreSQL.
- **Backend — FastAPI + Python:** expose a versioned API, authenticate users, validate inputs, enforce ownership, apply domain rules, persist records, and calculate analytics consistently.
- **Database — PostgreSQL:** store structured, related, durable records. Use SQLAlchemy for database access and Alembic migrations to version schema changes.
- **Object storage:** hold screenshot/file contents. Store their ownership, storage key, and related trade or plan in PostgreSQL; do not store large binary files in ordinary trade rows.
- **Workers/connectors:** perform MT5 imports, retry failed work, deduplicate external records, reconcile executions, and record sync health. Keep connector credentials and terminal access out of the browser.

The browser should communicate with the API over HTTPS. Prefer a same-origin route/proxy or a deliberately configured API origin. If the browser calls a separate API origin, configure a strict CORS allowlist and the chosen secure session-cookie policy; do not enable wildcard origins with credentials. Use secure, HTTP-only cookies or another reviewed session design. Never put database, broker, or signing secrets in frontend code.

## 2. Data model: one database, related tables

Every user-owned record must be scoped to its owner, directly or through an owned parent such as an account. Use internal UUID primary keys, foreign keys, timestamps, database constraints, and indexes for common account/date/filter queries. Use UTC for stored event timestamps; apply the user's timezone only when presenting or grouping those timestamps.

| Table | Stores | Main relationships and consumers |
|---|---|---|
| `users` | Login identity and account status | Owner of preferences, accounts, plans, journal records, and reviews |
| `user_preferences` | Timezone, display currency, theme, notification preferences | Settings, date displays, exports |
| `trader_profiles` | Optional experience, goals, preferred instruments/sessions | Onboarding and future personalisation |
| `trading_accounts` | User-named account, broker, account type, base currency, environment | Accounts, journal, snapshots, risk settings |
| `account_connections` | Connector type, connection status, sync cursor, last success/error metadata | Account connection status and import controls |
| `account_snapshots` | Timestamped balance, equity, margin, and free margin observations | Account overview and historical account charts |
| `trade_plans` | Intended symbol, direction, strategy/setup, thesis, entry/stop/target context, state | Quick capture, plans, plan-to-execution comparison |
| `plan_versions` | Before/after snapshots when an editable plan changes | Plan history and auditability |
| `trades` | User-facing journal episode linked to an account and optional plan | Journal, trade detail, review queue, analytics |
| `mt5_orders` | Broker order identifiers, requested type/volume/price, and state | Imported execution history |
| `mt5_deals` | Broker deal identifiers, fills, volume, execution time, and available costs/P&L | Reconciliation, realized results, trade timeline |
| `mt5_positions` | Current or observed broker position state | Open-position view and account reconciliation |
| `trade_events` | Entry, exit, partial close, modification, comment, and source event | Trade lifecycle timeline and reconciliation |
| `tradingview_alerts` | Received alert ID, symbol/timeframe, timestamp, payload, processing status | Future signal inbox and optional plan matching |
| `trade_alert_links` | Explicit or suggested alert-to-plan/trade associations | Signal context without treating an alert as a trade |
| `trade_reviews` | Plan adherence, learning, next action, and optional behavioral fields | Reviews and process analytics |
| `journal_tags` / `trade_tags` | Reusable labels and many-to-many trade labels | Journal filters and strategy/setup breakdowns |
| `risk_profiles` / `account_rule_sets` | User- and account-specific limits and evaluation rules | Risk status and warnings |
| `screenshots` | Private object key, upload metadata, timestamp, and linked plan/trade | Plan evidence and trade review |
| `sync_runs` | Import window, counts, status, errors, and reconciliation outcomes | Connection freshness and support diagnostics |
| `audit_logs` | Important security-sensitive and user-visible changes | Accountability and recovery |

### Key relationships and integrity rules

```text
users 1 ── many trading_accounts
users 1 ── many trade_plans
trading_accounts 1 ── many trades
trade_plans 1 ── zero-or-many trades
trades 1 ── many trade_events / trade_reviews / screenshots
trading_accounts 1 ── many MT5 orders / deals / positions / snapshots
trade_plans 1 ── many plan_versions
trades many ── many journal_tags
```

- A plan is trader intent; an execution is evidence that exposure existed. A plan with no fill remains a plan, even if it is discarded or invalidated.
- A `trades` row is a journal episode, not necessarily one broker order or one deal. One order may fill through multiple deals, and positions may have partial entries/exits. Preserve broker identifiers and model those records separately.
- Imported MT5 rows should retain their source and external identifiers. Enforce uniqueness in the correct scope, including per-account deal/order identifiers and `(account_id, external_id)` for reconciled MT5 journal episodes, so repeated imports do not duplicate records.
- A manual execution entry must remain labelled as user-reported and unverified. Do not merge it invisibly with broker evidence.
- An alert is an alert, not an executed trade. Matching an alert to a plan or execution should be explicit or clearly marked as a suggestion.
- Imported broker evidence should not be freely overwritten like a note. Record corrections or annotations separately and retain original source facts.
- Enforce ownership in backend queries and foreign keys. A supplied record ID is not proof that the current user owns that record.

## 3. Connect each TradeIQ feature

| Frontend feature | Read from | User actions and writes | What the UI should refresh |
|---|---|---|---|
| **Overview** | Current user's account summaries, closed/open trades, review coverage, and server-computed metrics | Date/account filters; navigate to a trade or review | Dashboard queries after a trade, review, import, or preference change |
| **Trade journal** | Paginated `trades`, joined with account/plan summaries and review status | Search/filter, open detail, CSV import/export, create a plan | Journal rows and counts after a saved plan, execution update, import, or review |
| **Trade plans / Quick capture** | `trade_plans` and their current state/version | Create/edit plan; discard/invalidate; record a fill linked to the plan | Plan list and associated journal episode after the API confirms the write |
| **Manual fill capture** | Selected plan and its account | Submit user-reported entry/exit/size/P&L and outcome | Trade detail, journal, review queue, and relevant analytics |
| **Reviews** | Closed eligible `trades` plus `trade_reviews` | Save or update plan adherence, learning, and a specific next action | Review status, overview coverage, and review-dependent analytics |
| **Analytics / P&L calendar** | Server-derived aggregates based on eligible closed trades and source data | Date range, account, strategy, and timezone filters | Refetch or invalidate affected aggregates after qualifying record changes |
| **Accounts** | `trading_accounts`, `account_connections`, latest snapshots, sync runs | Add/rename/archive account; connect/disconnect; request import | Account state, connection health, and last-sync timestamp |
| **Settings** | `user_preferences` and profile | Update timezone, currency, theme, and notification preferences | Preference display and all dependent date/currency formatting |
| **Future alerts / risk / evidence** | Alerts, risk profiles/rules, screenshot metadata | Acknowledge/link alerts; configure rules; upload evidence | Alert state, risk warnings, or linked evidence status |

For journal and analytics lists, the API should support server-side pagination, sorting, and filters rather than downloading every user's entire history. Return an explicit `last_synced_at` or equivalent freshness indicator for externally sourced account data.

## 4. Suggested versioned API contract

Use a consistent prefix such as `/api/v1`. These are proposed routes; implement and document request/response schemas before the frontend depends on them.

| Method and route | Purpose |
|---|---|
| `GET /api/v1/me` | Return the authenticated user's profile |
| `GET, PATCH /api/v1/preferences` | Read/update preferences |
| `GET, POST /api/v1/accounts` | List/create accounts |
| `GET, PATCH, DELETE /api/v1/accounts/{account_id}` | Read/update/archive an owned account |
| `GET /api/v1/accounts/{account_id}/status` (also `/connection`) | Connection and latest sync status |
| `GET /api/v1/accounts/{account_id}/positions` | Current open MT5 positions with observed prices and floating P&L |
| `POST /api/v1/accounts/{account_id}/connect`, `DELETE /connector-token` | Provision/rotate or revoke the one-time worker credential |
| `POST /api/v1/accounts/{account_id}/sync` | Queue an authorized import job |
| `GET /api/v1/accounts/{account_id}/sync-runs` | List sync history |
| `GET, POST /api/v1/plans` | List/create plans |
| `GET, PATCH /api/v1/plans/{plan_id}` | Read/update an owned plan and create a plan version when appropriate |
| `POST /api/v1/plans/{plan_id}/discard` | Mark an unfilled idea discarded without making a fake execution |
| `GET, POST /api/v1/trades` | Search/list or create a manual journal episode when appropriate |
| `GET, PATCH /api/v1/trades/{trade_id}` | Read/update permitted user-entered fields |
| `POST /api/v1/plans/{plan_id}/fills` | Record a user-reported fill against the plan |
| `GET /api/v1/trades/{trade_id}/events` (also `/timeline`) | Read the trade timeline |
| `GET /api/v1/trades/{trade_id}/journal`, `PATCH /journal/{section_key}` | Read and independently save bounded JSON journal sections |
| `GET /api/v1/integrations/tradingview/token` | Return only whether the user's webhook token is active |
| `GET, PUT /api/v1/trades/{trade_id}/review` | Read/create/update the review |
| `GET /api/v1/analytics/performance` | Return consistently defined performance totals and filters |
| `GET /api/v1/analytics/calendar` | Return daily P&L grouped for a requested date range/timezone |
| `GET /api/v1/analytics/by-strategy` | Return strategy/setup breakdowns |
| `GET, POST /api/v1/trades/{trade_id}/screenshots` | List/upload evidence metadata and issue a controlled upload flow |
| `POST /api/v1/alerts` and `GET /api/v1/alerts` | Future validated TradingView webhook ingestion and user alert listing |

For paginated endpoints, define a stable shape such as `{ "items": [], "next_cursor": null }` or a documented page/total format. For errors, return a stable code and safe user-facing message, with field-level validation details where applicable. The frontend must handle authentication expiry, validation errors, unavailable services, and retryable sync failures distinctly.

### Implemented backend routes and models

- `POST /api/v1/auth/register` — create a user and start a session.
- `POST /api/v1/auth/login` — verify credentials and start a session.
- `POST /api/v1/auth/logout` and `GET /api/v1/auth/me` — revoke the current session and inspect its user.
- `GET, PATCH /api/v1/me` and `GET, PATCH /api/v1/preferences` — profile and timezone/currency/theme settings.
- `GET, POST /api/v1/accounts` — create/list owned accounts.
- `GET /api/v1/accounts/{account_id}/connection` (also `/status`), `/history`, and `/positions` — connection/sync status, imported history, and current open positions.
- `POST /api/v1/accounts/{account_id}/connector-token` (also `/connect`), `DELETE /connector-token`, and `POST /sync` — issue/rotate or revoke a one-time scoped worker token and queue a sync.
- `GET /api/v1/connectors/mt5/accounts/{account_id}/sync-request` — worker-only claim endpoint.
- `POST /api/v1/connectors/mt5/accounts/{account_id}/sync` and `/sync-failure` — worker-only result endpoints.
- `GET, POST /api/v1/plans` — list/create plans; list supports `state`, `limit`, and `offset`.
- `GET, PATCH /api/v1/plans/{plan_id}` — read/update only an owned, still-planned idea.
- `GET, POST /api/v1/plans/{plan_id}/versions` — read or checkpoint plan history.
- `POST /api/v1/plans/{plan_id}/discard` — mark an owned, unfilled idea as discarded.
- `GET, POST /api/v1/trades`, `GET, PATCH /api/v1/trades/{trade_id}` — create/search journal records and edit permitted user fields.
- `GET /api/v1/trades/{trade_id}/events` (also `/timeline`), `GET /journal`, and `PATCH /journal/{section_key}` — event timeline and independently persisted journal sections.
- `GET, POST, PATCH /api/v1/trades/{trade_id}/reviews` — read/create/update a review.
- `GET /api/v1/dashboard/{summary,equity-curve,recent-trades}` and `/api/v1/analytics/{performance,by-strategy,by-session,risk}` — server-derived summaries.
- `GET /api/v1/risk/profiles`, `PUT /api/v1/accounts/{account_id}/risk-profile`, and `GET /api/v1/risk/{status,violations}` — configured limits and journal-derived warnings.
- `POST /api/v1/integrations/tradingview/token` and `DELETE .../token` — create/rotate or revoke a one-time, per-user webhook token.
- `GET /api/v1/integrations/tradingview/token` — return token configuration status without returning the secret.
- `POST /api/v1/webhooks/tradingview`, `GET /api/v1/alerts`, and alert match/dismiss routes — user-routed signal receipt and user-controlled links; alerts do not imply execution.
- `GET /healthz` and `GET /readyz` — process liveness and database readiness.

MT5 position-linked deals are reconciled into unified journal episodes keyed by account and position identifier. Partial exits keep the episode open while the position remains observed; the episode closes when the observed position disappears and recorded exit volume covers the entry volume. Gross deal P&L, commissions, and swap are included in lifecycle details. Reconciliation depends on sufficiently complete imported history; `inout` reversals are not yet split into close/open legs, and separate fee/balance operations are not imported.

The schema is in `backend/migrations/versions/0001_identity_and_plans.py`, `backend/migrations/versions/4df430e079c1_add_accounts_trades_and_platform_.py`, `backend/migrations/versions/86c8f4d9a8b1_add_mt5_worker_credentials.py`, `backend/migrations/versions/aa91c301df54_add_per_user_integration_tokens.py`, and the latest lifecycle migration. Database tables also cover MT5 orders, deals, positions, account snapshots, sync runs, account rule sets, screenshot metadata, notifications, audit logs, and hashed integration credentials; account rule evaluation and screenshot/notification providers remain incomplete. TradingView tokens are stored hashed, resolved to one user, and omitted from stored alert payloads. Analytics session buckets use UTC hours. Risk warnings use recorded trades and configured limits; they are not broker enforcement. The frontend uses several core APIs but its dashboard chart calculations are still client-side. Backend setup and validation instructions are in `backend/README.md`.

## 5. End-to-end user-input flow

Example: a user captures a plan and later records a manual fill.

1. The Quick capture form collects only plan fields and performs immediate client-side validation for usability.
2. A feature API function sends the typed payload to `POST /api/v1/plans`. The browser does not supply an authoritative owner ID.
3. FastAPI authenticates the session, validates the schema and domain rules, establishes the current user as owner, and calls a plan service.
4. The service inserts the plan and its initial version in one transaction. PostgreSQL constraints protect required fields and relationships.
5. The API returns the saved record, including its stable ID, state, and timestamps. The frontend updates the plans list from the response or refetches it.
6. When the user records a manual fill, the backend verifies ownership of the plan/account and stores the execution as user-reported evidence, keeping the plan's original intent unchanged.
7. The journal and dependent review/analytics views refresh from the API. Closed-trade metrics include only records meeting the documented eligibility/source rules.
8. If MT5 later supplies the corresponding execution, the connector stores the raw external order/deal first, deduplicates it, then reconciles it to a journal episode. It must not silently replace the manual record; conflicts or uncertain matches should be visible for review.

Client validation improves feedback but is not a security or integrity boundary. The backend repeats all validation and enforces permissions for every request.

## 6. Frontend integration pattern

Keep feature components separate from transport details. A practical structure as the Next.js app grows is:

```text
web/
├── app/
├── features/
│   ├── plans/       # forms, types, API functions, validation
│   ├── trades/
│   ├── reviews/
│   ├── accounts/
│   └── analytics/
└── lib/
    ├── api-client.ts
    ├── auth.ts
    └── validation.ts
```

Each feature should have typed request/response types, API functions, form validation, and tests. A shared `api-client.ts` should own the API base path, session behavior, JSON parsing, and conversion of non-success responses into explicit errors. Components should not hardcode URLs or database concepts.

When the server API is introduced:

1. Replace client-derived dashboard/analytics calculations with the server analytics endpoints, then add server-side pagination and filters.
2. Fetch the signed-in user's records on the server where appropriate, or from client components when interaction requires it.
3. For each mutation, show pending/error/success state and update or invalidate only affected queries.
4. Keep search, filters, pagination, timezone, and account selection in explicit UI/query state; send them to server endpoints when they affect returned data.
5. Keep the current CSV export/import semantics only after defining how server imports are validated, deduplicated, ownership-scoped, and reported to the user.
6. Add a deliberate migration/export path for existing browser-local data before asking users to switch devices. Do not silently upload demo/illustrative starter records as a user's real history.

For live account updates, persist and reconcile the event first, then notify the browser using Server-Sent Events or WebSockets if needed. On reconnect, the browser should refetch authoritative API data; a notification channel is not the system of record.

## 7. Analytics and source-of-truth rules

The API should own canonical financial and performance calculations so overview cards, the calendar, exports, and future reports do not implement subtly different formulas.

- Define which records count as closed, which sources are trusted, and how fees/commissions/swaps are treated.
- Prefer broker-reported realized values for imported trades. The current manual-entry UI asks for broker-reported realized P&L and does not calculate contract-specific profit; retain that distinction.
- Return calculation metadata or documented field definitions for metrics such as win rate, profit factor, average R, and net P&L.
- Exclude planned, discarded, and open records from closed-trade P&L calculations.
- Preserve raw UTC event time and apply the selected timezone only to display/calendar grouping.
- Do not treat a missing value as zero unless that metric's definition explicitly requires it.

## 8. Security, reliability, and operations

- Scope every read and write by the authenticated user and verify ownership of all referenced account, plan, and trade IDs.
- Validate request schemas and domain transitions on the backend. Use parameterized database access and least-privilege service credentials.
- Keep database credentials, MT5 secrets, webhook secrets, and session signing keys in managed server-side configuration; never log them or expose them in `NEXT_PUBLIC_*` variables.
- Authenticate and rate-limit integration endpoints. Validate TradingView payloads and deduplicate webhook deliveries.
- Use database transactions for related writes, unique constraints for duplicate prevention, and Alembic migrations for controlled schema evolution.
- Make sync status and failures visible. Retry transient failures safely and make import jobs idempotent.
- Maintain audit trails for material plan/rule changes and security-sensitive operations.
- Back up PostgreSQL and test restoration. Provide appropriate user export, disconnection, retention, and deletion procedures.
- Store screenshots privately, authorize every download, and avoid trusting a client-provided storage path.

## 9. Build and verify in vertical slices

Do not build every API and screen independently and connect them at the end. Complete one end-to-end slice at a time:

1. **Foundation:** FastAPI app, PostgreSQL, migrations, configuration, health checks, authentication, and ownership tests.
2. **Plans:** create/list/read/update/discard a plan from the UI through the API into PostgreSQL; verify persistence after reload and another authenticated session.
3. **Manual fills and reviews:** link a user-reported execution to its plan, then save and retrieve a review.
4. **Journal and analytics:** add server-side search/filter/pagination and canonical calculations over saved records.
5. **Accounts and MT5:** prove a supported connection method, history backfill, idempotent imports, partial-fill handling, reconciliation, and clear stale/error states.
6. **Evidence, alerts, and risk:** add only after the core data and permission contracts are tested.
7. **Production readiness:** verify migration deployment, backup restoration, auditability, monitoring, rate limits, and recovery behavior.

A feature is connected only when:

- A user input reaches a validated backend endpoint and the correct owned table.
- The API returns the saved record with a stable identifier.
- The frontend reflects the confirmed result and useful loading/error/empty states.
- The data remains available after reload and a new authenticated session.
- Invalid input is rejected without partial or inconsistent writes.
- One user cannot read or change another user's record by changing an ID.
- Repeated external imports do not duplicate records, and source/freshness are visible.
- Dashboard and export values agree with the documented server calculations.

## 10. Suggested initial backend layout

```text
backend/
├── app/
│   ├── api/           # FastAPI routers and dependencies
│   ├── schemas/       # Request/response validation models
│   ├── models/        # SQLAlchemy tables and relationships
│   ├── services/      # Domain rules and analytics
│   ├── repositories/  # Database query/persistence helpers
│   ├── integrations/  # MT5 and future TradingView adapters
│   ├── workers/       # Import, retry, and reconciliation jobs
│   └── core/          # Configuration, authentication, shared security
├── migrations/        # Alembic revisions
└── tests/             # Unit, API, database, permission, integration tests
```

Keep the service/repository split proportionate: routers should handle HTTP concerns, services should own domain behavior, and database operations should remain testable. Start with only the modules needed by the first vertical slice.
