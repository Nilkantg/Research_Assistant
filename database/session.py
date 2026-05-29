# database/session.py
#
# WHY THIS FILE EXISTS:
# This file answers "how do I connect to and talk to the database?"
# It provides three things:
#   1. Engines       — low-level database connections (sync + async)
#   2. Session factories — objects you use to run queries
#   3. Context managers  — safe patterns for opening/closing sessions
#
# WHY SYNC AND ASYNC BOTH:
# FastAPI route handlers are async functions. Calling blocking sync
# database code inside async functions freezes the entire event loop,
# blocking ALL concurrent requests. So route handlers must use the
# async engine. But simple startup scripts (like init_database) don't
# need async — sync is simpler and perfectly fine there.

import logging
from contextlib import contextmanager, asynccontextmanager
from typing import Generator, AsyncGenerator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

from config import get_settings
from database.models import Base

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------
# URL helpers
#
# SQLAlchemy requires different URL prefixes for sync vs async:
#   Sync:  sqlite:///./data/chat.db
#   Async: sqlite+aiosqlite:///./data/chat.db
#
# We store one canonical URL in settings and derive both from it.
# ---------------------------------------------------------------

def _get_sync_url(url: str) -> str:
    """Return the synchronous version of a database URL."""
    return url.replace("sqlite+aiosqlite:///", "sqlite:///")


def _get_async_url(url: str) -> str:
    """Return the async version of a database URL."""
    if "sqlite" in url and "+aiosqlite" not in url:
        return url.replace("sqlite:///", "sqlite+aiosqlite:///")
    return url


# ---------------------------------------------------------------
# Read settings once at module load.
# get_settings() is cached via @lru_cache, so this is free.
# ---------------------------------------------------------------
settings = get_settings()

_sync_url: str = _get_sync_url(settings.database_url)
_async_url: str = _get_async_url(settings.database_url)


# ---------------------------------------------------------------
# Engines
#
# Engines are expensive to create — they manage connection pools,
# parse the URL, load the driver. Create them ONCE at module load
# and reuse for the lifetime of the application.
# ---------------------------------------------------------------

sync_engine = create_engine(
    _sync_url,
    # SQLite only: allow connection to be shared across threads.
    # FastAPI's thread pool creates threads that need DB access.
    # Without this SQLite raises "SQLite objects created in a thread
    # can only be used in that same thread."
    # Not needed for PostgreSQL — remove this for Postgres.
    connect_args={"check_same_thread": False} if "sqlite" in _sync_url else {},
    # Echo=True logs every SQL statement. Useful in development to
    # verify correct queries are being generated. Disable in production.
    echo=settings.is_development,
)

async_engine = create_async_engine(
    _async_url,
    connect_args={"check_same_thread": False} if "sqlite" in _async_url else {},
    # Async SQL logging is very noisy — keep it off.
    echo=False,
)


# ---------------------------------------------------------------
# Session factories
#
# A Session is the SQLAlchemy object you use to run queries.
# Think of it like a "unit of work" — it tracks everything you've
# queried or changed, then commits it all as one atomic transaction.
#
# autocommit=False → you must explicitly commit. Nothing is saved
#                    until you call session.commit().
# autoflush=False  → pending changes are not sent to the DB until
#                    you commit. Gives you full control.
# ---------------------------------------------------------------

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    class_=AsyncSession,
    # expire_on_commit=False: after commit(), keep objects usable.
    # Default True means accessing obj.attribute after commit()
    # triggers a new DB query. False avoids that surprise.
    expire_on_commit=False,
)


# ---------------------------------------------------------------
# SQLite WAL mode — critical for any web server
#
# SQLite's default journal mode allows only ONE reader OR writer
# at a time. Under concurrent HTTP traffic this causes:
#   sqlalchemy.exc.OperationalError: database is locked
#
# WAL (Write-Ahead Logging) allows:
#   - Multiple readers simultaneously
#   - One writer, without blocking readers
#
# This listener fires on every new connection and applies the
# pragma settings before any queries run on that connection.
# ---------------------------------------------------------------

@event.listens_for(sync_engine, "connect")
def _apply_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Apply performance and correctness settings to each new SQLite connection."""
    if "sqlite" not in settings.database_url:
        return  # These pragmas are SQLite-only — skip for PostgreSQL

    cursor = dbapi_connection.cursor()
    # WAL mode: concurrent reads + one writer
    cursor.execute("PRAGMA journal_mode=WAL")
    # NORMAL sync: good balance between durability and speed.
    # FULL is safer but slower; OFF is fastest but risks corruption on crash.
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Enforce foreign key constraints at the SQLite level.
    # By default SQLite ignores FK violations — this turns that checking on.
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# ---------------------------------------------------------------
# Database initialization
#
# Creates all tables defined in models.py if they don't exist yet.
# Safe to call multiple times — SQLAlchemy checks before creating.
# Call this once in app/main.py lifespan startup.
# ---------------------------------------------------------------

def init_database() -> None:
    """
    Create all database tables defined in models.py.

    This is idempotent — if tables already exist, they are skipped.
    Existing data is never touched.

    NOTE: This does NOT handle migrations (schema changes to existing
    tables). For production schema changes, use Alembic.
    """
    logger.info(f"Initializing database: {_sync_url}")

    try:
        Base.metadata.create_all(bind=sync_engine)
        logger.info("Database tables created/verified")

        # Log which tables exist so startup logs confirm the schema
        with sync_engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            tables = [row[0] for row in result]
            logger.info(f"Active tables: {tables}")

    except Exception as exc:
        logger.error(f"Database initialization failed: {exc}")
        raise


# ---------------------------------------------------------------
# Context managers for safe session usage
#
# WHY CONTEXT MANAGERS INSTEAD OF MANUAL open/close:
# If an exception is raised mid-query, you might forget to close
# the session. Leaked sessions hold open connections. Enough leaked
# connections exhaust the pool and the app stops accepting requests.
#
# Context managers use try/finally — the session is ALWAYS closed,
# even when exceptions occur.
# ---------------------------------------------------------------

@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    """
    Synchronous database session as a context manager.

    Usage:
        from database import get_sync_db

        with get_sync_db() as db:
            session = db.query(ChatSession).filter_by(user_id="abc").first()
            # commit happens automatically on context exit
    """
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(f"Database error, transaction rolled back: {exc}")
        raise
    finally:
        session.close()


@asynccontextmanager
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async database session as a context manager.

    Use inside any async function (e.g. FastAPI background tasks,
    utility scripts that need async).

    Usage:
        from database import get_async_db

        async with get_async_db() as db:
            result = await db.execute(select(ChatSession))
            sessions = result.scalars().all()
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error(f"Async database error, transaction rolled back: {exc}")
        raise
    finally:
        await session.close()


async def get_db_dependency() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency-injection version of the async session.

    WHY A SEPARATE FUNCTION FROM get_async_db:
    FastAPI's Depends() requires a plain async generator function
    (one that uses `yield` without @asynccontextmanager).
    The @asynccontextmanager decorator changes the function signature
    in a way Depends() doesn't recognize. So we need both forms.

    Usage in a route:
        from database import get_db_dependency
        from fastapi import Depends
        from sqlalchemy.ext.asyncio import AsyncSession

        @router.get("/sessions")
        async def list_sessions(db: AsyncSession = Depends(get_db_dependency)):
            result = await db.execute(select(ChatSession))
            return result.scalars().all()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()