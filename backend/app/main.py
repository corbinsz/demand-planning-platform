import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.routers import dashboard, inventory, forecasting, purchase_orders, analytics, sync, promotions
from app.services.scheduler import start_scheduler, shutdown_scheduler

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import init_db
    logger.info("Initializing database...")
    await init_db()
    logger.info("Starting scheduler...")
    start_scheduler()
    yield
    logger.info("Shutting down scheduler...")
    shutdown_scheduler()


app = FastAPI(
    title="Inventory Intel — Demand Planning",
    description="AI-powered demand forecasting and inventory planning for Shopify + ShipHero stores. Predict what to reorder, when to reorder it, and how much.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(forecasting.router, prefix="/api/forecasting", tags=["Forecasting"])
app.include_router(
    purchase_orders.router, prefix="/api/purchase-orders", tags=["Purchase Orders"]
)
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(promotions.router, prefix="/api/promotions", tags=["Promotions"])
app.include_router(sync.router, prefix="/api/sync", tags=["Sync"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
