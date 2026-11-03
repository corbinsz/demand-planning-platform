# How to check that it works

Times below are Mountain Time, the clock in Utah. Nothing in this guide assumes Colorado.

## Fastest check

From the project folder:

```bash
./scripts/demo.sh
```

Then open http://127.0.0.1:5173/ . You should see the pitch, then **See today’s decisions**, then the Northline sample brand. Sign-in for that brand, if you want it, is `demo@northline.example` / `northline-demo`. That password is a public demo password. Do not reuse it for a real client.

Ctrl-C stops the app.

## Automated checks

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check app tests seed.py
.venv/bin/mypy app
.venv/bin/pytest -q
```

```bash
cd frontend
npm ci
npm run build
cd ..
node scripts/check-bundle.mjs
```

GitHub runs the same steps on every push (`.github/workflows/ci.yml`).

What the tests cover:

- Reorder math does not inflate an order when stock is healthy.
- A hero SKU stays in ABC class A.
- Croston holds its rate through quiet days. TSB fades.
- A promotion spike is not treated as the new normal.
- The backtest returns a non-negative range that contains the forecast.
- Two workspaces cannot see each other’s stock. Two warehouses are added, not double-counted.
- A share link and a PDF work. The PDF starts with `%PDF`.
- A promotion that ends before it starts is rejected.
- Deleting data requires the account email and then removes the promotion.
- Sync without a connection returns a sentence, not a stack trace.
- Shopify’s callback signature check accepts a real signature and rejects a fake one.
- Stored tokens encrypt and decrypt.

## Click-through

Use `docs/REVIEW-CHECKLIST.md`. That is the list for a person, not a test runner.

## Forecast proof

`docs/benchmark-results.json` is the last full run on the seeded Northline catalog (60 SKUs, about a year of orders). Re-run it with the demo database if you change the models. The API also returns the same summary at `/api/forecasting/model-report` after the cache is warm. The first forecast on a cold server takes well under a minute; after that it is cached for 30 minutes.

## What a green check does not prove

It does not call a real Shopify or ShipHero account. Connect those only on a server whose `DEMO_MODE` is false and whose `SECRET_KEY` is a long random value.
