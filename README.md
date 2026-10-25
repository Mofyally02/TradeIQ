# Trade Journal App

A modern trading journal and decision-intelligence platform for discretionary MT5 traders who want to review execution quality, validate trading plans, and improve performance over time.

This project is built around the strategic product blueprint in [Trade_Journal_App_Research_and_Implementation_Blueprint-1.pdf](./Trade_Journal_App_Research_and_Implementation_Blueprint-1.pdf) and translates the research into a practical implementation roadmap for a functional, production-ready trading workflow application.

## Overview

The Trade Journal App is not just a log of closed trades. It is a structured system for capturing the full trading story:

- Market facts: what the terminal reported
- Trader intent: what was planned
- Behavior: what the trader actually did and learned

This creates a trustworthy record of the relationship between the trading plan, the execution, and the review process. The central product promise is simple: preserve decision timing, reconcile trading records, and explain process quality before interpreting profits.

## Implementation Status

The frontend foundation is in [`web/`](./web/), using Next.js, React, and TypeScript. It now uses the separate [`backend/`](./backend/) FastAPI API for authentication, accounts, plans, journal trades/sections, reviews, timezone preferences, and MT5/TradingView credential workflows. The API and Alembic-managed PostgreSQL schema also cover dashboard/analytics, risk profiles, and TradingView alert ingestion. Dashboard/analytics calculations and several advanced settings/features remain client-side or unfinished; the former browser workspace is preserved and can be exported/imported through CSV.

Implemented in the current increment:

- workspace navigation for overview, journal, trade plans, reviews, analytics, and accounts
- trade journal search and outcome filters
- quick capture for pre-trade plans, with planned ideas kept separate from executed trades
- manual fill capture with entry, stop loss, take profit, and position size; a recorded fill stays open until explicitly closed with user-reported realized P&L
- timestamped setup, emotion, execution, and trade-management journal entries, with updates available from the trade journal
- account setup cards for MT5 server/login metadata and TradingView alert labels; passwords and webhook secrets are never collected by this browser prototype, and setup does not activate synchronization
- explicit idea discard and no-exposure states
- post-trade reviews for plan adherence, learning, and next action
- browser-local persistence for plans, fills, and reviews
- CSV export for the current journal search/filter results
- performance and strategy summaries derived from recorded closed trades
- an Overview date-range picker with all-time, 7/30/90-day, and custom-date filters for dashboard metrics, chart, recent activity, and review coverage
- an analytics P&L calendar with month/year views, daily and weekly totals, timezone-aware grouping, and per-day trade/hourly drill-down
- responsive desktop and mobile layouts

Still outstanding for a production R1 release: PostgreSQL deployment and production operations; authentication hardening such as rate limiting and recovery flows; account-rule evaluation; validating MT5 worker capture/backfill and reconciling imported deals into journal episodes; object-storage uploads; live updates; production monitoring/recovery; and production validation. The worker requires a Windows host with a logged-in MT5 terminal and has not been validated against a live broker. Browser storage is not encrypted application storage and is not suitable for passwords, API keys, webhook secrets, or as a source of broker truth. Starter account balances and trades are illustrative; manually entered execution values are user-reported and unverified. This build is not a live trading or broker-reconciled risk-monitoring system.

### Run the current app

Requirements: Homebrew with PostgreSQL 14 or later, Python 3.11 or later, Node.js 20.9 or later, and npm.

For first-time setup, install backend dependencies:
```bash
cd backend
brew install postgresql@14
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Start the backend API and PostgreSQL database in one terminal:
```bash
bash backend/start-dev.sh
```

In a second terminal, install the frontend dependencies once and start the frontend:
```bash
cd web
npm ci
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The frontend connects to the API at [http://localhost:8000](http://localhost:8000); the backend startup script applies database migrations before the API starts. Docker Compose is an optional backend alternative. Setup and shutdown details are in [`backend/README.md`](./backend/README.md). From the repository root, use `npm --prefix web run lint` and `npm --prefix web run build` to validate the app.

In the browser, use the Overview date-range control to filter dashboard metrics and activity by all time, the last 7/30/90 days, or a custom inclusive date range. Create a plan from **Quick capture**, then open **Trade plans** to manually record a fill or discard the idea. Fill details remain open until you explicitly mark the exposure closed and enter realized P&L; this prototype does not automatically read broker fills or calculate contract-specific profit. In **Trade journal**, use **Update trade** / **Journal** to record entry, stop loss, take profit, size, and timestamped emotion/setup/execution/management notes. In **Accounts**, add an MT5 or TradingView setup using non-secret metadata only; no passwords or API/webhook secrets are accepted, and sync remains inactive. In **Analytics**, the P&L calendar groups closed trades by the selected timezone and supports monthly daily/weekly totals, a yearly heatmap, and a selected-day trade/hourly breakdown. Account setup metadata, journal entries, plans, fills, and the selected calendar timezone are retained in that browser's local storage. Use **Export CSV** from the journal to download trade notes and filtered records before changing browsers or clearing site data.

## Product Vision

The app helps traders answer critical questions such as:

- Did the trade match the original plan?
- Was the risk controlled and the execution disciplined?
- Did the strategy and process create repeatable edge?
- What are the areas for improvement across accounts, timeframes, and rules?

The platform is designed for discretionary MT5 traders, including:

- live traders
- evaluation and funded account traders
- developing traders building review habits
- mentors and coaches reviewing selected records with permission

## Core Principles

The blueprint emphasizes several important principles that guide product design:

1. Separate measurements from interpretation
   - Profit is not proof of execution quality.
   - Behavior evidence does not imply causation.

2. Preserve context before hindsight changes it
   - Intent, notes, screenshots, and trade plan information must be captured in real time.

3. Quality before advanced AI features
   - Replay, behavioral analysis, AI summaries, and prop monitoring require reliable data capture.

4. Account isolation and trust
   - Each account must remain independently auditable, secure, and recoverable.

5. Decision coverage over vanity metrics
   - The app should focus on whether a trade was planned, executed, reviewed, and improved.

## North-Star Metric

The product's success is defined by complete decision-and-review coverage.

- Coverage = qualifying closed episodes / all eligible closed episodes
- A qualifying episode includes:
  - reconciled execution data
  - a plan recorded before the first fill
  - a linked strategy or an explicit discretionary label
  - a completed review containing a specific next action

This prioritizes completeness and decision quality rather than raw P&L alone.

## Key Functionalities

### 1. MT5 Integration and Trade Capture

The application should connect directly to MetaTrader 5 to:

- sync account data
- import historical trades and account activity
- ingest live trade events and positions
- maintain reliable identifiers for orders, deals, and fills
- reconcile broker data with trader notes and plans

This layer provides the system of record for the terminal data and ensures the journal reflects actual execution.

### 2. Decision Capture and Trade Planning

Before the trade is executed, users should be able to record:

- trade idea or plan
- strategy or setup name
- market context
- triggers and entry criteria
- stop-loss and take-profit logic
- confidence level
- risk parameters
- pre-trade checklist or rule alignment

The system supports both structured trade planning and quick capture for fast-moving situations.

### 3. Trade Lifecycle Management

The blueprint explicitly recommends two linked state machines:

- idea / plan state
- executed exposure state

This avoids fictional trades and distinguishes between:

- watching or ready
- pending order
- no exposure until filled
- live episode
- add / reduce / exit / close states
- cancelled or invalidated ideas

This ensures the platform remains accurate and prevents noise in the review process.

### 4. Journal Review and Behavioral Logging

Users can review each trade after execution and record:

- what went well
- what went wrong
- emotional state
- process adherence
- mistakes or rule violations
- lessons learned
- next action

This becomes the behavioral layer that allows the trader to learn beyond raw numbers.

### 5. Performance Analytics

The app includes a dashboard for reviewing performance using clear metrics such as:

- win rate
- average win / average loss
- profit factor
- expectancy
- R-multiple
- drawdown
- risk-adjusted outcomes
- MAE and MFE analysis
- trade quality scores
- strategy performance breakdowns

The analytics layer should help traders and coaches answer not just "Did I make money?" but "Was my process sound?"

### 6. Risk and Rule Monitoring

The app supports configured risk rules and operational guardrails such as:

- daily loss floors
- account-specific rule checks
- consistency thresholds
- rule breaches and resets
- account headroom and funded-account conditions

This is especially important for evaluation or prop-style traders who need rule compliance visibility.

### 7. Screenshots, Context, and Evidence Capture

Each trade can include:

- chart screenshots
- terminal screenshots
- notes and reflections
- strategy tags
- emotional or psychological markers
- account context

These become key evidence artifacts when analyzing trade quality and review completeness.

### 8. Calendar, Summaries, and Reporting

The journal should support:

- daily review summaries
- weekly performance recaps
- monthly trend analysis
- full trade-export reporting
- custom breakdowns by strategy, session, account, or instrument

This helps users form a consistent review habit without excessive admin overhead.

### 9. Multi-Account Support

The app is designed to support:

- multiple live accounts
- funded account environments
- demo accounts
- evaluation account tracking
- account-level isolation and independent rule settings

This allows traders to compare performance across their portfolio while keeping each environment separated and auditable.

### 10. Export and Data Portability

The app should support:

- exportable trade history
- structured reporting
- local backup or downloadable archives
- deletion and data control options
- audit-friendly retention standards

This is critical for trust, compliance, and migration readiness.

## User Experience Design

The product should prioritize clarity and speed. The blueprint recommends a high-trust experience where the platform shows the trader what happened without mixing it with speculation.

Key UX principles:

- Terminal facts and trader intent remain clearly separated
- Quick capture is prioritized over complex forms
- Plans and reviews are visible in context
- Trade pages show timeline, execution, notes, and feedback together
- Risk and performance analysis are easy to compare across strategies

The app should aim to reduce friction in both planning and post-trade review, because reliability and habit formation are core to its value.

## Functional Architecture

A recommended architecture for the product includes the following layers:

### Frontend

- responsive web app
- dashboard and trade analytics views
- review flows and journal entry forms
- account management and user profile pages
- charts, reports, and review summaries

### Backend

- API layer for account, trade, plan, and review data
- authentication and authorization system
- MT5 integration service
- synchronization and reconciliation engine
- risk and validation services
- export/report generation services

### Data Layer

- relational database for structured journal records
- account and strategy metadata tables
- execution event history and trade lifecycles
- user notes, screenshots, and review artifacts
- audit logs for changes and access

### Integration Layer

- MetaTrader 5 data connectors
- broker historical import
- optional charting and market data providers
- future AI or coaching summarization services

### Security and Compliance Layer

- secure authentication
- role-based access control
- account isolation
- revocable sharing for mentors and coaches
- export/deletion and user data controls
- protected storage of sensitive trading and account records

## Recommended Product Structure

The blueprint organizes the app into three release stages.

### R1: Core MVP

Target: approximate first 16 weeks

In scope:

- authentication
- account management
- MT5 capture and historical backfill
- correct aggregation and reconciliation
- live position status
- versioned trade plans
- quick notes
- screenshots
- strategy tagging
- basic emotional tracking
- P&L and performance records
- calendar and simple reporting
- export and deletion support

Quality gates:

- account isolation works consistently
- supported broker pilot succeeds
- recovery and data integrity are dependable
- trade capture usability is validated

### R2: Advanced Review

Target: additional 8–12 weeks

In scope:

- configurable prop rules
- checklists and process grading
- daily and weekly review workflows
- data-qualified MAE and MFE analysis
- event and chart replay
- transparent behavioral flags
- constrained AI summaries with human review

Quality gates:

- each feature has a data-quality contract
- scenario tests are defined
- human review validates the interpretation layer

### R3: Research Analytics

Target: after R2, depending on data quality and adoption

In scope:

- deeper counterfactual analysis
- process-model safety checks
- more advanced behavioral and decision quality metrics
- research-grade reporting
- simulation and experimentation support
- stronger AI-assisted coaching under explicit human review constraints

This phase focuses on turning the journal into a rich analytical engine rather than a simple ledger.

## Workflow Design

The app must manage both the trading idea and the actual trade independently, while linking them logically.

### Trade Idea Workflow

Possible states:

- watching
- ready
- pending order
- invalidated
- discarded

### Executed Exposure Workflow

Possible states:

- live episode
- add
- reduce
- exit
- close
- canceled or invalidated exposure

This structure avoids converting no-trade decisions or cancelled ideas into fake trade entries and keeps the system grounded in evidence.

## Data Model Highlights

The product should treat trades as structured records rather than narrative-only notes.

Core entities:

- User
- Account
- Strategy
- Trade Idea / Plan
- Order / Fill / Execution Event
- Position / Exposure
- Review / Journal Entry
- Screenshot / Evidence Asset
- Tag / Label
- Risk Rule
- Performance Summary

This model supports thoughtful analytics while keeping the app operationally simple for daily traders.

## Product Roadmap

### Phase 1 — Discovery and validation

Objectives:

- validate the product thesis against real MT5 workflows
- confirm supported broker and account data flows
- refine data quality expectations
- define review process and ownership model

Deliverables:

- technical requirements
- account and data flow mapping
- risk and integrity rules
- pilot design

### Phase 2 — Core journal and MT5 connectivity

Objectives:

- capture trades reliably
- reconcile journal data with broker records
- enable plan capture and structured review

Deliverables:

- login and account management
- trade import and synchronization
- trade lifecycle tracking
- review notes and screenshots
- dashboard and basic summaries

### Phase 3 — Performance intelligence

Objectives:

- provide actionable analytics
- review work quality, not just profits
- track risk headroom and rule compliance

Deliverables:

- risk dashboards
- MAE/MFE and behavioral features
- strategy breakdown reports
- calendar-based review views

### Phase 4 — Advanced coaching and experimentation

Objectives:

- scale analysis beyond the single trade
- raise quality of patterns and process feedback
- support research-oriented product features

Deliverables:

- replay and event review
- recommendation engine with human oversight
- advanced experiment-ready reports
- optional AI support with strict boundaries

## MVP Acceptance Criteria

The initial product should be accepted only when the following are true:

- users can record and reconcile trading plans with actual execution
- MT5 data import is accurate and reliable
- multiple accounts can remain isolated and auditable
- review workflows are easy enough to sustain over time
- screenshots and notes are attached to the right trade state
- reports show meaningful performance and risk context
- export and deletion flows are operationally usable

## Success Criteria

The platform should be considered successful when it improves the quality of decision review and reduces the gap between trading intent and executed behavior.

A strong success signal is when users can consistently answer:

- What was the plan?
- What happened in the terminal?
- How did the trader respond?
- What should they do differently next time?

## Suggested Technology Stack

The selected web-app direction is Next.js, React, and TypeScript, with PostgreSQL planned for persistent structured records. The app is being developed in vertical slices; the existing prototype does not yet connect to a database or broker.

- Frontend and initial application API: Next.js App Router / React / TypeScript
- Recommended backend API: FastAPI / Python, with SQLAlchemy and Alembic for database access and migrations
- Persistent data: PostgreSQL, introduced with account isolation and data migrations
- MT5 integration: a separate connector/integration service, validated against supported broker and terminal behavior
- Evidence storage: private object storage for screenshots and attachments
- Background processing: synchronization and reconciliation jobs with observable retries
- Security and operations: authentication, authorization, audit events, backups, logging, and monitored recovery

The recommended backend, database, and frontend mapping—including proposed tables, relationships, API routes, feature flows, and rollout steps—is documented in the [Backend, Database, and Frontend Integration Blueprint](./docs/backend-database-frontend-integration.md). A FastAPI backend and Windows MT5 worker implementation now exist, but live deployment and frontend integration remain outstanding. Prioritize reliable capture, data integrity, security, and auditability over adding infrastructure before it is needed.

## Recommended Next Steps

1. Validate the product with a small pilot on real MT5 users.
2. Confirm data quality contracts for trade capture and synchronization.
3. Scope the MVP around the R1 requirements only.
4. Build a core dashboard focused on decision coverage and process review.
5. Expand into advanced review analytics after the system proves trustworthiness.

## Summary

The Trade Journal App is a serious decision record and execution intelligence product designed for traders who want to improve beyond raw profit numbers. Its strongest value lies in accountability: connecting intent, execution, and review into one coherent process.

The platform is best executed in phases, beginning with trustworthy data capture and review, then layering in analytics, risk review, and advanced coaching features only after the data quality is proven.

This makes the project realistic, testable, and scalable from an MVP into a high-value research and analytics platform for serious traders.

---

Built from the product research and implementation blueprint dated 8 October 2026.
