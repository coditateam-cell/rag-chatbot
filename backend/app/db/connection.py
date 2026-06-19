"""
Async database connection and session management for the RAG Chatbot Application.

Uses SQLAlchemy's async engine backed by asyncpg (PostgreSQL).
Connection parameters are read from environment variables so no secrets
are hard-coded.

Environment variables
---------------------
POSTGRES_USER     : database username          (default: postgres)
POSTGRES_PASSWORD : database password          (default: postgres)
POSTGRES_DB       : database name              (default: ragchatbot)
POSTGRES_HOST     : hostname / service name    (default: postgres)
POSTGRES_PORT     : TCP port                   (default: 5432)
"""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------

USE_LOCAL_MODE = os.getenv("USE_LOCAL_MODE", "false").lower() == "true"

if USE_LOCAL_MODE:
    _DATA_DIR = Path("./data")
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = "sqlite+aiosqlite:///./data/database.db"
else:
    _DB_USER = os.getenv("POSTGRES_USER", "postgres")
    _DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    _DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
    _DB_PORT = os.getenv("POSTGRES_PORT", "5432")
    _DB_NAME = os.getenv("POSTGRES_DB", "ragchatbot")

    DATABASE_URL = (
        f"postgresql+asyncpg://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
    )

# ---------------------------------------------------------------------------
# Async engine
# ---------------------------------------------------------------------------

if USE_LOCAL_MODE:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
    )
else:
    engine = create_async_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False,
    )

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncSession:  # type: ignore[override]
    """Async generator that yields a database session for FastAPI dependencies."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

if USE_LOCAL_MODE:
    _SCHEMA_PATH = Path(__file__).parent / "schema_sqlite.sql"
else:
    _SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def init_db() -> None:
    """Read schema.sql (or schema_sqlite.sql) and execute it against the database.

    Splits multi-statement SQL into individual statements because asyncpg
    does not support multiple commands in a single prepared statement call.
    Uses ``IF NOT EXISTS`` guards so it is safe to run on an already-initialised database.
    """
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")

    # Split into individual statements, skip empty ones
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    async with engine.begin() as conn:
        for statement in statements:
            if USE_LOCAL_MODE:
                await conn.exec_driver_sql(statement)
            else:
                await conn.exec_driver_sql(statement)
