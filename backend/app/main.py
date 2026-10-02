import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app import db, worker
from app.config import get_settings
from app.metrics import MetricsMiddleware
from app.routers import auth, invoices

log = logging.getLogger("provenn")


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop = asyncio.Event()
    task = None
    if get_settings().run_worker:
        task = asyncio.create_task(worker.run_forever(stop))
        log.info("in-process worker enabled")
    yield
    stop.set()
    if task:
        await task
    await db.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ProveNN Reimburse API", version="1.0.0", lifespan=lifespan)

    app.add_middleware(MetricsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Partner-Key"],
        expose_headers=["Content-Disposition"],
    )

    @app.get("/healthz", tags=["ops"])
    async def healthz():
        try:
            async with db.engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            log.exception("health check: database unreachable")
            return JSONResponse({"status": "db_unavailable"}, status_code=503)
        return {"status": "ok"}

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    async def metrics_endpoint():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(auth.router)
    app.include_router(invoices.router)
    return app


app = create_app()
