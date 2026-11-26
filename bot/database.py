from __future__ import annotations

import logging

import asyncpg

LOGGER = logging.getLogger(__name__)


class Database:
    """Optional PostgreSQL connection pool."""

    def __init__(self, dsn: str | None) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    @property
    def connected(self) -> bool:
        return self._pool is not None

    async def connect(self) -> None:
        if not self._dsn:
            LOGGER.info("DATABASE_URL not set; running without database.")
            return
        self._pool = await asyncpg.create_pool(self._dsn, min_size=0, max_size=3)
        LOGGER.info("Connected to PostgreSQL.")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
