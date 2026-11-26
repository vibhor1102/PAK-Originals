from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

FWASTATS_BASE_URL = "https://fwastats.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class FwaStatsError(RuntimeError):
    """Raised when fwastats.com returns an error or unexpected payload."""


@dataclass(frozen=True, slots=True)
class MemberWeight:
    """Single clan member record from fwastats Members.json."""

    tag: str
    name: str
    town_hall: int | None
    weight: int | None
    in_war: bool | None
    rank: int | None
    role: str | None


def normalize_tag(raw_tag: str) -> str:
    """Normalize a Clash of Clans tag to uppercase with leading '#'."""
    cleaned = raw_tag.strip().upper().replace(" ", "")
    if not cleaned:
        raise ValueError("Clan tag cannot be empty.")
    return cleaned if cleaned.startswith("#") else f"#{cleaned}"


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


def parse_member_weights(payload: Any) -> list[MemberWeight]:
    """Parse fwastats Members.json payload into MemberWeight records."""
    if not isinstance(payload, list):
        raise FwaStatsError(f"Expected a JSON list from fwastats, got {type(payload).__name__}.")

    members: list[MemberWeight] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        members.append(
            MemberWeight(
                tag=str(item.get("tag") or "").strip(),
                name=str(item.get("name") or "Unknown").strip(),
                town_hall=_coerce_int(item.get("townHall")),
                weight=_coerce_int(item.get("weight")),
                in_war=_coerce_bool(item.get("inWar")),
                rank=_coerce_int(item.get("rank")),
                role=str(item.get("role") or "").strip() or None,
            )
        )
    return members


class FwaStatsClient:
    """Async HTTP client for fwastats.com endpoints."""

    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={"User-Agent": USER_AGENT},
            )

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def fetch_clan_members(self, clan_tag: str) -> list[MemberWeight]:
        """Fetch member war weights for a clan from fwastats.com."""
        normalized = normalize_tag(clan_tag)
        url = f"{FWASTATS_BASE_URL}/Clan/{normalized.lstrip('#')}/Members.json"

        await self.start()
        assert self._session is not None

        try:
            async with self._session.get(url) as response:
                if response.status != 200:
                    raise FwaStatsError(f"fwastats.com returned HTTP {response.status} for {normalized}.")
                payload = await response.json(content_type=None)
        except FwaStatsError:
            raise
        except aiohttp.ClientError as exc:
            raise FwaStatsError(f"Failed to reach fwastats.com: {exc}") from exc
        except ValueError as exc:
            raise FwaStatsError("fwastats.com returned invalid JSON.") from exc

        return parse_member_weights(payload)
