# TradeIQ local development startup

## Requirements

- Homebrew with PostgreSQL 14 or later
- Python 3.11 or later with the backend dependencies installed
- Node.js 20.9 or later and npm

## 1. Start the backend and database

For a first-time setup, install PostgreSQL and the backend dependencies:

```bash
cd backend
brew install postgresql@14
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

In the first terminal, from the repository root, start PostgreSQL and the API with one
command:

```bash
bash backend/start-dev.sh
```

The script starts the Homebrew PostgreSQL service if needed, creates the local `tradeiq`
database if it does not exist, applies migrations, and starts the API. The frontend uses
`http://localhost:8000` by default, and the API accepts the local frontend origins.
Check database/API readiness at [http://localhost:8000/readyz](http://localhost:8000/readyz);
the response should be `{"status":"ready"}`.

## 2. Start the frontend

In a second terminal, from the repository root:

```bash
cd web
npm ci
npm run dev
```

`npm ci` is needed for the initial setup (and again after frontend dependency changes).
Then open [http://localhost:3000](http://localhost:3000).

## Stop the services

Press `Ctrl+C` in the backend terminal to stop the API. PostgreSQL remains available as a
Homebrew service. To stop PostgreSQL too, run `brew services stop postgresql@14`.

Docker Compose is also available as an alternative if Docker Desktop is installed:
from `backend/`, run `docker compose up --build`.
## MT5 methods and admin

- Two MT5 methods: **MetaApi** (hosted, needs `METAAPI_TOKEN`) and **EA** (MQL5 Expert Advisor pushes to a per-account webhook; `backend/ea/TradeIQ_Journal.mq5`, also served at `/TradeIQ_Journal.mq5`).
- Clients no longer set the EA up by hand: after Connect, the wizard offers a personal one-click installer (`TradeIQ-Setup.command` for Mac, `TradeIQ-Setup.bat` for Windows, served by `/api/v1/mt5/ea/<id>/<secret>/installer/<os>`). It installs and compiles the EA, writes the settings, starts the bridge as a background service and relaunches MT5.
- If MT5 rejects WebRequest (error 4014), set the EA input `UseFileBridge=true` and run `python backend/ea/bridge.py "<MT5 data folder>/MQL5/Files" "<webhook url>"`; the bridge forwards the EA's files to the webhook.
- For the EA, set `PUBLIC_API_URL` to a public HTTPS URL and allow it in MT5: Tools → Options → Expert Advisors → Allow WebRequest.
- Admin panel: `/admin`. Create or reset the admin: `cd backend && ../.venv/bin/python -m app.cli create-admin --email allansaiti02@gmail.com --name "Allan Saiti"`.
- The admin sets the platform default method and per-user overrides; switching a user disconnects their accounts of the other method.

## Multi-account detection and switching

- **Accounts → Detect my MT5 accounts** issues a per-user connector (`POST /api/v1/devices/connector`) and opens the setup wizard. Run the downloaded installer once; re-running rotates the connector secret.
- Any account logged into that MT5 terminal is reported to `/api/v1/mt5/device/{user}/{secret}` and shows a **Connect account / Not now** prompt (`GET /devices/detected`). Connecting requires re-entering the account login and server, which must match.
- The top-bar **Account** switcher scopes trades, plans, reviews and overview balance/equity to one account (`?account_id=`), or **All accounts**. The choice is remembered in the browser.
- Plans now carry `account_id` (migration `a9b3d6e2f410`; run `alembic upgrade head`).
- Set a public HTTPS `PUBLIC_API_URL` for real users; the EA must be recompiled after updating (`backend/ea/TradeIQ_Journal.mq5`).

### Install once, add accounts freely
Adding an MT5 account on the platform and choosing the EA method installs the per-user connector only the first time (`already_installed: true` afterwards). Any later account you add is connected automatically the moment you log into it in MT5; accounts you did not add yet appear as a Connect prompt. Use **Switch to this account** on the Accounts page (or the top-bar switcher) to change which account the journal shows.
