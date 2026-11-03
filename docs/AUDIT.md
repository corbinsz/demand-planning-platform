# Audit of the original app

This is a plain-English review of the code as it stood before the product work in this branch. It covers bugs, edge cases, data quality, security, and performance. `CHANGES.md` says what we did about each item.

The app is a demand-planning tool: a Python API (FastAPI), a React screen, and a database. It is meant to read Shopify orders and ShipHero warehouse stock, then suggest what to reorder.

## What would stop a demo or a Docker install

1. **Docker Compose would not boot.** The Compose file requires `backend/.env`, and that file is not in the repo (correctly — it would hold secrets). Compose treats a missing env file as a hard error.
2. **The database driver for Postgres was not installed.** The app asks for Postgres (`asyncpg`) and the migration tool asks for a normal Postgres driver, but neither package was in `requirements.txt`.
3. **Startup ran database migrations that do not exist.** Compose runs `alembic upgrade head`, but there is no `alembic/versions` folder, so Alembic exits with an error.
4. **The API would ignore Postgres even after the above was fixed.** A setting called `use_sqlite` defaults to on. In the container the API would create a SQLite file and never read the Postgres service.
5. **The screen could not reach the API inside Docker.** The React dev server proxies `/api` to `localhost:8000`. Inside the frontend container, localhost is the frontend itself, not the API.
6. **Date queries only work on SQLite.** Sales charts and forecasts group days with `strftime`, which Postgres does not have. A real Postgres install would 500 on the dashboard chart and on every forecast.
7. **There were no automated tests.** Nothing checked that a change still worked.

## Forecasting bugs and limits

8. **One model for every product.** Holt-Winters exponential smoothing is a good fit for steady, seasonal sellers. It is a poor fit for sizes that sell a few units and then go quiet (intermittent demand). Those SKUs were still forced through the same model.
9. **The same model was fit three times.** A 30-day, 60-day, and 90-day forecast each trained from scratch. Slower, and the three horizons could disagree with each other.
10. **No backtest.** Nothing checked a forecast against what actually sold later. There was no way to know if the model was any good, and no confidence range on the number.
11. **Promotions were stored and never used.** A Black Friday spike stayed in the history and could be treated as the new normal. Upcoming promotions did not raise the forecast.
12. **Reorder quantities could only grow.** Each night the app saved the suggested buy quantity back onto the rule, and the next run treated that saved number as a minimum. A one-time suggestion became a permanent floor.
13. **Suggested buys ignored “we are fine on stock.”** If a rule had a reorder quantity, the suggestion was at least that big even when the warehouse was full.
14. **Stock used for the forecast could be counted twice.** The forecast added up every ShipHero snapshot ever stored for a SKU. The dashboard, by contrast, tried to use the latest snapshot. After a few syncs those two screens would disagree, and the forecast number would inflate.
15. **Multi-warehouse stock was under-counted in some places and over-counted in others.** The dashboard’s “latest snapshot” is the single newest row, so the second warehouse disappeared. The SKU popup did the same. Reconciliation also kept one warehouse per SKU when two warehouses shared a timestamp, the join could double the row.
16. **“Below reorder” on the dashboard was too sensitive.** It counted a SKU if *any* old snapshot was under the reorder point, not the current one.

## Data-quality issues

17. **Demo data was modeled on a real brand name (Otishi), including product titles.** A sales demo should use an obviously fictional catalog so a prospect never thinks they are looking at someone else’s business.
18. **Shopify snapshot quantities in the seeder could go negative** when a small random adjustment was applied to a zero-stock item.
19. **Dead stock and excess stock valued inventory at the selling price, not the cost.** That overstates how much cash is trapped in the warehouse.
20. **Reconciliation compared different kinds of numbers.** It subtracted ShipHero on-hand from Shopify available. Those are not the same measure, so healthy SKUs looked “off.”
21. **Seeded job names did not match the names the status screen looks up** (`shopify_sync` vs `shopify_full_sync`). The setup screen could say a job had never run even though the seeder had written a success row.
22. **Dates mixed timezone-aware and timezone-naive values.** Python throws if you compare those. Several screens (promotions “is this active?”, reconciliation, dead stock) were one database dialect away from a 500.
23. **ABC classes could mis-label the best seller.** Class was chosen *after* adding the SKU’s share. A product that is 90% of revenue landed in class B instead of A. The same off-by-one pushed the SKU that crosses 80% into B.

## Edge cases

24. **ShipHero sync started immediately on boot** (the “every 4 hours” job’s default is to run once at startup) and called the real API with the placeholder token.
25. **The purchase-order screen called ShipHero on every page load.** With no real token it showed a raw error instead of the recommendations we can already compute from orders.
26. **A reorder rule could be saved for a SKU that does not exist.**
27. **Promotions allowed an end date before the start, and a discount outside 0–100.**
28. **Search treated `%` and `_` as wildcards**, so a literal search could match far more than the user typed.
29. **The in-memory forecast cache was never cleared after a sync or a reseed,** so the screen could show the previous catalog for up to 30 minutes.
30. **Errors returned the internal exception text to the browser.** That can leak table names, file paths, or upstream API messages.
31. **An empty catalog or an all-zero sales history** was mostly guarded, but Holt-Winters can still fail or return negative demand. Negatives were clipped only on the success path of one helper.

## Security and privacy

This mattered more once the goal became “hold a real brand’s Shopify and ShipHero data.”

32. **No accounts and no separation between brands.** Every endpoint was open. Anyone who could reach the port could read orders, trigger a sync, or change reorder rules.
33. **Store tokens lived in environment variables and in the process,** not in an encrypted column scoped to one workspace. One leaked env file would expose the token, and two brands on one server would have shared it.
34. **The setup screen’s main path was “paste the Admin API token into a file.”** That token is powerful, easy to commit by accident, and hard to rotate per brand.
35. **Shopify scopes were documented as read-only in the setup page, but nothing in the connect flow enforced a scope list,** because there was no connect flow.
36. **No audit log.** No record of who connected a store, exported a report, or deleted data.
37. **No data-deletion path.** A brand that left could not wipe orders, stock, or tokens from the database.
38. **No Terms or Privacy page,** even as a placeholder for the owner to replace.
39. **CORS, a default `SECRET_KEY` of `change-me`, and placeholder tokens shipped as code defaults.** Fine for a laptop demo, unsafe the moment the process is reachable on a network.
40. **Shareable reports did not exist,** so the only way to show a client was to hand over the whole app, including sync buttons.

## Performance

41. **Forecast math ran on the web server’s event loop.** Holt-Winters is CPU work. While it ran, the API could not serve other requests.
42. **No single-flight guard on the forecast cache.** Two browsers opening the page at once both retrained every SKU.
43. **Inventory list returned every snapshot row,** not the current one per warehouse. After months of syncs the page would grow without bound.
44. **Dashboard “units on hand” and several reports scanned snapshots without a workspace or “latest per warehouse” constraint.** Fine on the seeded sample, slower and wrong after real syncs.
45. **N+1 queries were mostly already avoided** in forecasting and reconciliation (good). The remaining cost was the modeling, not the SQL.

## What was already in good shape

- The React screens are structured, readable, and already look like a product rather than a debug page.
- Shopify and ShipHero clients already retry on rate limits.
- ABC, dead stock, and excess stock exist as real reports with CSV export.
- The seeder builds a year of seasonal orders, two warehouses, and deliberate stockouts — a solid base for a demo once the brand is fictional and the stock math is fixed.
- Secrets were not committed. `.env` is gitignored. `.env.example` uses obvious placeholders.
