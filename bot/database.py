from __future__ import annotations

import logging

import asyncpg

from .fwastats import MemberWeight, normalize_tag

LOGGER = logging.getLogger(__name__)

CREATE_MEMBER_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS clan_member_history (
    clan_tag TEXT NOT NULL,
    player_tag TEXT NOT NULL,
    name TEXT NOT NULL,
    town_hall INTEGER,
    weight INTEGER,
    in_war BOOLEAN,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_in_war_at TIMESTAMPTZ,
    PRIMARY KEY (clan_tag, player_tag)
);
"""


class Database:
    """Optional PostgreSQL store for remembering departed clan/war members."""

    def __init__(self, dsn: str | None) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    @property
    def connected(self) -> bool:
        return self._pool is not None

    async def connect(self) -> None:
        if not self._dsn:
            LOGGER.info("DATABASE_URL not set; running without member history persistence.")
            return
        self._pool = await asyncpg.create_pool(self._dsn, min_size=0, max_size=3)
        async with self._pool.acquire() as conn:
            await conn.execute(CREATE_MEMBER_HISTORY_SQL)
        LOGGER.info("Connected to PostgreSQL and ensured clan_member_history table.")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def record_clan_members(self, clan_tag: str, members: list[MemberWeight]) -> None:
        """Upsert current clan members so departed members can be recalled later."""
        if self._pool is None or not members:
            return

        norm_clan = normalize_tag(clan_tag)
        rows = [
            (
                norm_clan,
                normalize_tag(m.tag),
                m.name,
                m.town_hall,
                m.weight,
                m.in_war,
            )
            for m in members
            if m.tag.strip()
        ]
        if not rows:
            return

        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO clan_member_history (
                    clan_tag, player_tag, name, town_hall, weight, in_war,
                    last_seen_at, last_in_war_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6,
                    NOW(), CASE WHEN $6 IS TRUE THEN NOW() ELSE NULL END
                )
                ON CONFLICT (clan_tag, player_tag) DO UPDATE SET
                    name = EXCLUDED.name,
                    town_hall = COALESCE(EXCLUDED.town_hall, clan_member_history.town_hall),
                    weight = COALESCE(EXCLUDED.weight, clan_member_history.weight),
                    in_war = EXCLUDED.in_war,
                    last_seen_at = NOW(),
                    last_in_war_at = CASE
                        WHEN EXCLUDED.in_war IS TRUE THEN NOW()
                        ELSE clan_member_history.last_in_war_at
                    END
                """,
                rows,
            )

    async def get_recent_departed_members(
        self,
        clan_tag: str,
        *,
        exclude_tags: set[str],
        limit: int,
    ) -> list[MemberWeight]:
        """Fetch recently seen members who are no longer in the current roster."""
        if self._pool is None or limit <= 0:
            return []

        norm_clan = normalize_tag(clan_tag)
        excluded = [normalize_tag(tag) for tag in exclude_tags if tag.strip()]
        async with self._pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT player_tag, name, town_hall, weight
                FROM clan_member_history
                WHERE clan_tag = $1
                  AND NOT (player_tag = ANY($2::text[]))
                ORDER BY last_in_war_at DESC NULLS LAST, last_seen_at DESC
                LIMIT $3
                """,
                norm_clan,
                excluded,
                limit,
            )

        return [
            MemberWeight(
                tag=row["player_tag"],
                name=row["name"],
                town_hall=row["town_hall"],
                weight=row["weight"],
                in_war=False,
                rank=None,
                role=None,
            )
            for row in records
        ]
