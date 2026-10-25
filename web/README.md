# TradeIQ web app

This is the Next.js App Router application for TradeIQ Journal. Product scope, roadmap, and current implementation status are documented in the [repository README](../README.md).

## Development

Requirements: Node.js 20.9 or later and npm.

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Useful checks:

```bash
npm run lint
npm run build
```

The app uses the FastAPI backend as its source of truth for sign-in, accounts, trade plans, manual and imported journal episodes, journal sections, reviews, and the timezone preference. Set `NEXT_PUBLIC_API_URL` to the API origin (defaults to `http://localhost:8000`) and configure the backend's `WEB_ORIGINS` to include the frontend origin. The API uses an HTTP-only session cookie; the browser never receives database or broker credentials. Plan/trade/review/account writes are sent to the API, and the Accounts view provisions/revokes MT5 worker credentials, queues syncs, and provisions/revokes the TradingView webhook token. One-time credentials are held only in component memory and shown in a dedicated copy dialog.

Some presentation work is still local: dashboard and analytics charts calculate from the API-loaded records rather than using every server analytics endpoint; filters are not yet server-paginated. Profile/currency/theme settings, evidence uploads, alert review, risk controls, WebSocket/SSE updates, and one-click migration of the former `localStorage` workspace are not complete in this frontend. The prior browser data is not overwritten, and CSV import is uploaded to the authenticated API. PostgreSQL and the Windows MT5 worker still require deployment; live-terminal synchronization has not been validated. See the repository [README](../README.md) and [backend setup](../backend/README.md) for status and instructions.
