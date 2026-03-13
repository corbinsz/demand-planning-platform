# Demand Planning Platform — Inventory Management Tool

A full-stack demand planning application with Shopify and ShipHero API integrations for DTC e-commerce brands. Forecast demand, prevent stockouts, and automate reorders — instead of guessing what to buy and when.

## What it does

| Feature | Description |
|---------|-------------|
| **Demand Forecasting** | Holt-Winters exponential smoothing with seasonality detection per SKU. Predicts 30/60/90-day demand and calculates days until stockout. |
| **Reorder Automation** | Generates purchase order suggestions ranked by urgency. Factors in lead time, safety stock, and current velocity. Export to CSV. |
| **ABC Classification** | Pareto analysis ranking SKUs by revenue contribution (A = top 80%, B = next 15%, C = bottom 5%). Know where to focus. |
| **Dead Stock Detection** | Finds SKUs with inventory but no sales. Estimates capital at risk and recommends liquidation or discounting. |
| **Overstock Alerts** | Flags SKUs with more inventory than needed based on sell-through rate and target coverage days. |
| **Inventory Reconciliation** | Compares Shopify vs ShipHero stock levels, flags discrepancies, and calculates daily velocity from order history. |
| **Stock Drawdown Charts** | Per-SKU projection showing when you'll stock out at current sell rate, with reorder point overlay. |
| **Promotional Periods** | Track promos and sales events so the forecasting engine can account for demand spikes. |

## Tech Stack

**Backend:** Python, FastAPI, SQLAlchemy (async), Pandas, Statsmodels, APScheduler
**Frontend:** React 18, Vite, Recharts, React Router
**Database:** SQLite (dev), PostgreSQL (prod via Docker)
**Integrations:** Shopify Admin REST API, ShipHero GraphQL API

## Quick Start

### Local Development

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
cp .env.example .env          # edit with your API keys
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

### Seed Demo Data

```bash
cd backend
python -m seed
```

Populates the database with 60 SKUs modeled after a DTC fitness brand (shoes, apparel, accessories), 365 days of order history with seasonal patterns, and realistic inventory snapshots across two warehouses.

### Docker

```bash
docker compose up --build
```

Starts PostgreSQL, backend (port 8000), and frontend (port 5173).

## Project Structure

```
backend/
  app/
    main.py              # FastAPI app, startup, CORS
    config.py            # Pydantic settings from .env
    database.py          # SQLAlchemy async engine + session
    models/models.py     # Product, Order, InventorySnapshot, ReorderRule, etc.
    routers/
      dashboard.py       # KPI summary endpoint
      inventory.py       # Stock levels, reconciliation, SKU detail
      forecasting.py     # Demand forecasts, reorder alerts
      analytics.py       # ABC, dead stock, excess stock + CSV export
      purchase_orders.py # PO suggestions, reorder rules CRUD
      promotions.py      # Promotional period CRUD
      sync.py            # Trigger Shopify/ShipHero sync
    services/
      forecasting.py     # Holt-Winters engine, batch forecast generation
      analytics.py       # ABC classification, dead/excess stock analysis
      reconciliation.py  # Cross-source inventory comparison
      shopify_sync.py    # Shopify API sync with rate limiting
      shiphero_sync.py   # ShipHero GraphQL sync with retry + backoff
      scheduler.py       # APScheduler job configuration
  seed.py                # Demo data seeder

frontend/
  src/
    pages/
      Home.jsx           # Dashboard with KPI cards + sales trend chart
      Inventory.jsx      # Stock table with search, filters, card/table view
      Forecasting.jsx    # Demand forecasts with urgency filters + chart
      Reports.jsx        # ABC, dead stock, excess stock tabs
      PurchaseOrders.jsx # PO suggestions + open orders from ShipHero
      Promotions.jsx     # Promotional period management
      Setup.jsx          # API connection configuration
    components/
      KPICards.jsx       # Dashboard metric cards with tooltips
      InventoryTable.jsx # Sortable, paginated inventory table
      ProductCards.jsx   # Card view for inventory
      ForecastChart.jsx  # Urgent vs. volume forecast bar charts
      SkuDetailModal.jsx # Full SKU detail with drawdown projection
      POGenerator.jsx    # Purchase order suggestions + CSV export
      ReorderAlerts.jsx  # Reorder urgency alerts
      Sidebar.jsx        # Navigation sidebar
      shared/            # InfoTooltip, Pagination, SortableHeader, tableStyles
    services/api.js      # Axios API client
```

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (Docker) or leave blank for SQLite |
| `SHOPIFY_STORE_DOMAIN` | `your-store.myshopify.com` |
| `SHOPIFY_ACCESS_TOKEN` | Shopify Admin API access token |
| `SHIPHERO_API_TOKEN` | ShipHero API bearer token |
| `SECRET_KEY` | Random string for session security |
| `CORS_ORIGINS` | Comma-separated allowed origins |

## API Highlights

- **Rate limiting**: Shopify sync respects the leaky bucket (40 req, 2/sec refill) with proactive throttling. ShipHero sync has exponential backoff with 5 retries and GraphQL throttle detection.
- **Batch queries**: Forecast generation uses 4 batch queries instead of N+1 per-SKU loops.
- **Caching**: Forecasts are cached for 30 minutes to avoid recomputation on every page load.
- **CSV export**: All report tabs (ABC, dead stock, excess stock) have one-click CSV download.

## License

MIT
