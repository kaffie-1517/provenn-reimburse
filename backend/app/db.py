from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def connect_options(url: str) -> tuple[str, dict]:
    """Adapts libpq-style URLs (as hosted Postgres providers hand out) to asyncpg.

    - `sslmode=...` isn't understood by asyncpg; it becomes the `ssl` argument.
    - PgBouncer in transaction mode (e.g. port 6543) can't keep prepared
      statements, so asyncpg's statement cache is turned off there.
    """
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    connect_args: dict = {}
    sslmode = query.pop("sslmode", None)
    if sslmode and sslmode != "disable":
        connect_args["ssl"] = "require" if sslmode in ("require", "prefer", "allow") else sslmode
    if query.pop("pgbouncer", None) == "true" or parts.port == 6543:
        connect_args["statement_cache_size"] = 0
        query["prepared_statement_cache_size"] = "0"
    return urlunsplit(parts._replace(query=urlencode(query))), connect_args


def engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        url, connect_args = connect_options(get_settings().database_url)
        _engine = create_async_engine(url, pool_pre_ping=True, connect_args=connect_args)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as session:
        yield session


async def dispose() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine, _sessionmaker = None, None
