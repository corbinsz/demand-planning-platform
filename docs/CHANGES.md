# What changed, and why

## Second pass

The forecast gain on the smooth sample was small, so the second pass only kept methods that beat Holt-Winters on a situation it handles badly:

- **Parent forecast, split by size.** A rare size borrows the parent’s seasonality instead of being fit on a string of zeros. On a synthetic six-size shoe, that top-down forecast beat per-size Holt-Winters by more than 5% (demand-weighted MASE). It is in the model race, and a size uses it only when its own replay agrees.
- **Stockout days are not treated as “nobody wanted it.”** If we know the warehouse was empty, those zeros are filled with the usual weekday demand before fitting. On a censored seasonal series, that cut the error against the demand that was actually there.
- **A rising trend.** Holt-Winters beats “repeat last week” when demand is climbing. That stays.
- **SBA** (the usual Croston bias correction) is available for intermittent SKUs and is used only when the replay says it is better. It is not forced.
- **Pooled gradient boosting** now sees day-of-week, month, and which parent a SKU belongs to. Per-SKU boosting was dropped from the race: it was the slow piece and it lost.
- **Ranges got narrower in an honest way.** A 30-day total no longer adds the worst daily miss thirty times. The band grows with the square root of the number of days, so it stops saying “somewhere between 0 and 80” for a forecast of 25.

Reorder math now refills safety stock even when recent sales are zero, and the order quantity includes safety stock. Tests went from 15 to 39, including tenant isolation (one brand cannot read, edit, share, or delete the other).

Hosted preview: there is no Render login on this machine, so there is no live URL yet. `docs/PREVIEW.md` is the one-click path (Deploy to Render). The site is one container: the API serves the built pages, so the owner does not run Docker locally.

## First pass

The audit of the original app is in `docs/AUDIT.md`. This file is what we did about it, for an owner who does not live in the code. The product owner is in Utah. Copy that mentions a clock uses Mountain Time (Utah). The sample brand’s main warehouse is Salt Lake City, not a Colorado site. There was no Colorado assumption in the old docs; the new ones do not add one.

## The idea of the product

The first screen used to be a dashboard of charts. It is now a landing page that says the value in one line, then a **Today** screen: what will stock out, what to buy, and how much cash is stuck. Charts are still there, one click down. That is the “simple on the surface” rule.

## Bugs and Docker

- Postgres drivers (`asyncpg`, `psycopg`) are installed. Compose no longer requires a missing `.env`, no longer runs Alembic migrations that did not exist, and no longer forces SQLite while a Postgres container is sitting there.
- Inside Docker, the website proxies API calls to the `backend` service instead of its own localhost.
- Day grouping uses `date()`, which works on SQLite and Postgres. The old `strftime` calls crashed on Postgres.
- Datetimes are stored as UTC without a timezone flag, so comparisons do not throw.
- Stock is the latest snapshot per warehouse, then summed. Forecasts no longer add up history. The dashboard no longer drops the second warehouse.
- Reconciliation compares available to available.
- ABC class is chosen before a SKU’s share is added, so a product that is most of revenue stays in class A.
- Suggested buy quantities no longer ratchet upward every night. A supplier minimum applies only when an order is needed.
- Seeded Shopify quantities cannot go negative. Job names match the status screen.
- Errors returned to the browser are sentences. Internal text stays in the log.
- Search treats `%` and `_` as ordinary characters.
- Scheduled jobs do not call Shopify or ShipHero on boot, and they skip a workspace that is not connected.
- The sample catalog is a fictional brand, Northline Athletics. It is not modeled on a real label.

## Forecasting

`backend/app/services/forecast_engine.py` runs a rolling-origin backtest of seasonal naive, Holt-Winters, Croston, TSB, and gradient boosting (per SKU and one global model). The catalog winner is the best demand-weighted MASE. A SKU keeps its own winner only when it beats that by at least 5%. Ranges are an 80% band from the replay, and they always contain the point forecast.

On the seeded catalog (`docs/benchmark-results.json`, 60 SKUs):

| Policy | Demand-weighted MASE |
| --- | --- |
| Repeat last week | 1.02 |
| Always Holt-Winters (the old policy) | 0.73 |
| Selected mix | 0.72 |

Holt-Winters won the catalog. Nine SKUs took a different method because it was clearly better on their history. Croston and TSB were tried and did not win on this smooth sample. That is the honest result. The harness is what makes a later, burstier catalog switch on evidence instead of on a slogan.

Promotions are stripped out of history before fitting and applied to future days.

## Accounts, privacy, and sharing

- Workspace plus user. Every business table is scoped to the workspace.
- Passwords are hashed. Sign-in tokens expire. Login is rate-limited.
- Shopify OAuth with read-only scopes. ShipHero refresh-token exchange. Tokens encrypted with a key derived from `SECRET_KEY`.
- Audit log. Delete imported data. Delete the account. Both require the owner to type their email.
- Read-only share link and PDF for stockout risk, reorders, and dead stock.
- Terms and Privacy pages are placeholders and say so.
- The server refuses to start in non-demo mode with a known default secret.
- Security headers on every response. Client errors can be posted to `/api/client-errors` with no third-party script. Analytics stay off unless `VITE_ANALYTICS_ENDPOINT` is set, send no cookies, and honor Do Not Track.

## Today, alerts, and the Monday email

`GET /api/today` is the home screen payload. Alerts are sentences: stockout in N days, reorder soon, overstock. `GET /api/digest` is the weekly email. It is sent only when SMTP or a webhook is configured. The schedule is Monday 8:00am Mountain Time (Utah).

## Screens

- Landing page at `/`.
- Today at `/today`, with Why? on the three decisions.
- Buy list, forecast (model name and range), stock, quiet stock, more numbers, promotions, connections.
- Focus rings, skip link, higher-contrast body text, labels on forms, status that is not color alone.
- Narrow windows get a Menu button.
- Bundle budget: all JavaScript gzipped stays under 350 KB (`scripts/check-bundle.mjs`). The entry chunk is about 75 KB gzipped. Chart code loads only on the pages that need it.

## Files, grouped

New backend: `app/security.py`, `app/deps.py`, `app/timeutil.py`, `app/sqlutil.py`, `app/services/forecast_engine.py`, `reorder.py`, `stock.py`, `credentials.py`, `shopify_oauth.py`, `shiphero_auth.py`, `alerts.py`, `deletion.py`, `reporting.py`, `audit.py`, routers `auth`, `integrations`, `reports`, `account`, `system`, tests under `backend/tests/`.

Rewritten or heavily edited: `app/main.py`, `app/config.py`, `app/database.py`, `app/models/models.py`, `app/services/forecasting.py`, `analytics.py`, `reconciliation.py`, `scheduler.py`, `shopify_sync.py`, `shiphero_sync.py`, routers `dashboard`, `inventory`, `forecasting`, `analytics`, `purchase_orders`, `promotions`, `sync`, `seed.py`.

Frontend: `App.jsx`, `main.jsx`, `index.css`, `pages/Landing.jsx`, `Today.jsx`, `Login.jsx`, `Legal.jsx`, `ShareReport.jsx`, `components/Explain.jsx`, `ConnectPanel.jsx`, `session.jsx`, `analytics.js`, `monitoring.js`, plus copy and columns on Forecast, Buy, Connections, and More numbers.

Ops: `docker-compose.yml`, `backend/requirements.txt`, `requirements-dev.txt`, `backend/.env.example`, `frontend/Dockerfile`, `frontend/vite.config.js`, `scripts/demo.sh`, `scripts/check-bundle.mjs`, `.github/workflows/ci.yml`, `pyproject.toml`.

Docs: this file, `ARCHITECTURE.md`, `PRODUCT.md`, `TESTING.md`, `DEPLOY.md`, `REVIEW-CHECKLIST.md`, `AUDIT.md`, `benchmark-results.json`.

## Extra things added because they made the product clearer

- A landing page that states the value before asking anyone to connect a store.
- “Why?” on the decisions, instead of only tooltips buried in tables.
- In-app alerts and a weekly email hook that does not send unless configured.
- A performance budget checked in CI.
- Privacy-friendly analytics and error hooks with no third-party SDK in the bundle.
- Accessibility pass: contrast, focus, skip link, form labels, reduced motion.
- The sample brand and its warehouse placed in Utah so a demo does not imply some other headquarters.
