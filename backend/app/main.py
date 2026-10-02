import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import db
from app.config import get_settings
from app.routers import auth

log = logging.getLogger("provenn")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await db.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ProveNN Reimburse API", version="1.0.0", lifespan=lifespan)

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

    app.include_router(auth.router)
    return app


app = create_app()
