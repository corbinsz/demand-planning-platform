# Demand Planning Platform

[![CI](https://github.com/corbinsz/demand-planning-platform/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/corbinsz/demand-planning-platform/actions/workflows/ci.yml)

Forecasts SKU demand from order history, flags stock that will run out before a replenishment arrives, and suggests a purchase quantity.

Corbin Szenegeto built this in spare time to practice a full stack (FastAPI, React, Postgres, Docker) on that planning problem. The catalog that ships with the app is invented. You run it on your own machine.

![Dashboard with the forecast-accuracy card for the synthetic catalog](docs/screenshots/dashboard-hero.png)

## Run it locally

One command with Make. It runs Docker Compose, which starts Postgres, the API, and the site, and loads the demo catalog into an empty database.

```bash
make
```

The same stack without Make:

```bash
docker compose up --build
```

Open http://localhost:8080. The API docs are at http://localhost:8000/docs.

The first launch fits a forecast the first time you open Forecasting or Purchase Orders, and it fits the accuracy backtest the first time you open the dashboard. Those passes are the slow ones. Each result is cached for 30 minutes.

To run the processes yourself instead of in containers:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m seed
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

cd frontend
npm install
npm run dev
```

The Vite dev server is http://localhost:5173 and proxies `/api` to port 8000. `python -m seed` writes a SQLite file, `backend/inventory.db`.

## Run it yourself / host it yourself

Nothing in this repo deploys the app. There is no live site, and there is no config that publishes one when you push.

To run it on a machine you control:

1. Copy `.env.example` to `.env`.
2. Set `USE_SQLITE=false`, point `DATABASE_URL` at your Postgres, and set `SECRET_KEY` and `POSTGRES_PASSWORD` to values you choose.
3. Leave the Shopify and ShipHero tokens as `replace-me` unless you want the sync jobs to call those APIs with your own credentials.
4. `make`, or `docker compose up --build`.
5. If anyone besides you should open it, put your own TLS reverse proxy in front of port 8080. Do not commit real tokens.

The Dockerfiles are production-style: the API runs under uvicorn without reload, and the React app is a built bundle served by nginx. nginx proxies `/api` to the `backend` service.

## What you can do in the demo

- Dashboard totals: units on hand, 30-day orders and revenue, sell-through, reorder count, and a rough daily revenue figure for SKUs that are already at zero.
- A forecast-accuracy card: weighted absolute percentage error and bias for Holt-Winters against a seasonal-naive baseline, overall and per SKU.
- A year of synthetic orders, so the sales chart and the forecasts have a history.
- Inventory by warehouse, plus a comparison of the demo "store" count and the demo "warehouse" count.
- A 30/60/90 day forecast per SKU, and a reorder suggestion when stock will not cover supplier lead time.
- ABC labels, dead stock, and excess stock, each exportable as CSV.
- A small promotion calendar. Those rows are stored and shown. They are not fed into the forecast.

![Inventory for the synthetic catalog](docs/screenshots/inventory.png)

![Purchase suggestions ranked by urgency](docs/screenshots/purchase-orders.png)

## Architecture

```mermaid
flowchart LR
  browser[Browser]
  nginx[nginx static site]
  api[FastAPI]
  db[(Postgres)]
  forecast[Holt-Winters forecast]
  shopify[Shopify API]
  shiphero[ShipHero API]

  browser --> nginx
  nginx -->|/api| api
  api --> db
  api --> forecast
  shopify -.->|only with your token| api
  shiphero -.->|only with your token| api
```

Local `uvicorn` uses SQLite instead of Postgres. The same schema is created on startup.

## How forecasting works / how accurate it is

For each SKU the app builds a daily sales series for the last year and fills days with no orders as zero. A day that is wildly above the SKU's usual sales is pulled back to the average, so one bulk order does not set the forecast. If about two months of history show a weekly or monthly repeat, Holt-Winters exponential smoothing is fit with a weekly seasonal term. Otherwise it is fit with a trend only. Fewer than two weeks of history, or a fit that fails, falls back to "recent daily average times the number of days."

The reorder point is that recent daily rate times the supplier lead time, plus safety stock. A saved rule can raise the point, not lower it. The suggested buy covers about eight weeks of that daily rate, minus what is already on hand. Urgency is how that runway compares with lead time: inside the lead time is critical, inside 1.5x is high, inside 2x is medium, and beyond that is low.

Stock is the newest count in each warehouse, added together. Older snapshots stay in the table so a later sync does not erase history, but they are not treated as extra units.

### How accurate it is on the sample catalog

The dashboard card is a rolling-origin backtest of that same 30-day forecast (`GET /api/forecasting/backtest`).

- Each holdout is the next 30 days of unit sales. The windows do not overlap.
- The newest 30 days are scored when at least 120 days of history come before them. Earlier holdouts step back 60 days.
- Holt-Winters is the forecast the reorder page uses, including the weekly seasonal term when the training window shows a repeat.
- The baseline is seasonal naive: each future day copies the sales from 7 days earlier.
- WAPE is total absolute error divided by total actual units, pooled across every SKU and holdout. A SKU that sells more counts more.
- Bias is (forecast − actual) / actual, with the same weights. A negative bias means the forecast was low.

On the synthetic catalog seeded on 19 November 2026, every one of the 55 SKUs had four holdouts (220 in total):

| Model | WAPE | Bias |
| --- | --- | --- |
| Holt-Winters | 0.3796 (shown as 38.0%) | −0.2195 (shown as −22.0%) |
| Seasonal naive | 0.4098 (shown as 41.0%) | −0.0855 (shown as −8.6%) |

Holt-Winters is 3.0 percentage points of WAPE better than repeating the last week, and it under-forecasts by more. That is a small gain on this catalog. The worst row is a low-volume size, `VE-SH-PM-13`: 18 units across the holdouts, Holt-Winters WAPE 1.1111, bias −0.5556. A miss of a few units is a large percentage there. The 38.0% headline is weighted by units, so that row does not set it.

Seeding again on a later day moves the retail calendar, because weekend and month effects follow the seed date. The card is the measurement for the database you are looking at. These orders are synthetic. The errors are not a result from a live store.

## Tests

GitHub Actions on `main` and on pull requests runs:

- Backend: ruff, black, mypy, pytest with coverage
- Frontend: eslint, vitest, production build
- `docker build` for the API image and the nginx image

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest

cd frontend
npm ci
npm test
npm run lint
npm run build
```

## Limits

- One catalog, no login, no tenants.
- Promotions are a calendar only. The forecast does not raise or lower demand for them.
- The first forecast of the full demo catalog is a statsmodels fit per SKU, and the accuracy backtest is another fit at every holdout. Later loads in that process use a 30-minute memory cache.
- The backtest scores the synthetic history the seed just wrote. It is not a claim about a real catalog.
- Shopify and ShipHero sync are optional. With the placeholder tokens, those jobs do not call out. This app does not push orders back to those systems.
- ABC, dead stock, and excess stock are straightforward revenue and coverage rules, not a causal model.
- This is a portfolio project built in spare time. It does not have customers, and the numbers on the screen are the synthetic catalog.

## License

[MIT](LICENSE)
