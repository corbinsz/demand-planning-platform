import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import (
    account,
    analytics,
    auth,
    dashboard,
    forecasting,
    integrations,
    inventory,
    promotions,
    purchase_orders,
    reports,
    sync,
    system,
)
from app.security import assert_runtime_safety
from app.services.scheduler import shutdown_scheduler, start_scheduler

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_runtime_safety()
    from app.database import init_db
    logger.info("Initializing database...")
    await init_db()
    if settings.auto_seed:
        from seed import seed_if_empty
        created = await seed_if_empty()
        if created:
            logger.info("Seeded the fictional Northline Athletics demo workspace")
    start_scheduler()
    if settings.warm_forecasts:
        import asyncio
        asyncio.create_task(_warm_forecasts())
    yield
    shutdown_scheduler()


async def _warm_forecasts():
    from sqlalchemy import select

    from app.database import async_session
    from app.models.models import Workspace
    from app.services.forecasting import generate_all_forecasts
    try:
        async with async_session() as session:
            ids = [row[0] for row in (await session.execute(select(Workspace.id))).all()]
        for workspace_id in ids:
            await generate_all_forecasts(workspace_id)
        logger.info("Forecast cache warmed for %s workspace(s)", len(ids))
    except Exception:
        logger.exception("Forecast warm-up failed")


app = FastAPI(
    title="Inventory Intel",
    description="What to reorder, what is about to stock out, and where cash is stuck. For Shopify brands that fulfill with ShipHero.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})


app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(system.router, prefix="/api", tags=["Today"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(forecasting.router, prefix="/api/forecasting", tags=["Forecasting"])
app.include_router(purchase_orders.router, prefix="/api/purchase-orders", tags=["Purchase Orders"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(promotions.router, prefix="/api/promotions", tags=["Promotions"])
app.include_router(sync.router, prefix="/api/sync", tags=["Sync"])
app.include_router(integrations.router, prefix="/api/integrations", tags=["Integrations"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(account.router, prefix="/api/account", tags=["Account"])


@app.get("/api/health")
async def health():
    from sqlalchemy import text

    from app.database import async_session
    database = "ok"
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        database = "error"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "demo_mode": settings.demo_mode,
    }
