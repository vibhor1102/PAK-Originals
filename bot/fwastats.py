from __future__ import annotations

from dataclasses import dataclass
import math
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


TH_COUNT_KEYS: tuple[tuple[str, str], ...] = (
    ("TH19", "th19Count"),
    ("TH18", "th18Count"),
    ("TH17", "th17Count"),
    ("TH16", "th16Count"),
    ("TH15", "th15Count"),
    ("TH14", "th14Count"),
    ("TH13", "th13Count"),
    ("TH12", "th12Count"),
    ("TH11", "th11Count"),
    ("TH10", "th10Count"),
    ("TH9", "th9Count"),
    ("TH8", "th8Count"),
    ("TH<=7", "thLowCount"),
)


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


@dataclass(frozen=True, slots=True)
class ClanSummary:
    """Single FWA clan summary from fwastats Clans.json."""

    tag: str
    name: str
    estimated_weight: int | None
    weight_submit_date: str | None
    th_counts: dict[str, int]


def weight_to_th_band(weight: int | None) -> int | None:
    """Map a war weight to its 10k-wide TH band: (170k, 180k] -> 18, (180k, 190k] -> 19."""
    if weight is None or weight <= 0:
        return None
    return math.ceil(weight / 10_000)


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


def parse_war_members(payload: Any) -> list[MemberWeight]:
    """Parse fwastats WarMembers.json payload into MemberWeight records."""
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
                in_war=True,
                rank=_coerce_int(item.get("position")),
                role=None,
            )
        )
    return members


def parse_clan_summaries(payload: Any) -> list[ClanSummary]:
    """Parse fwastats Clans.json payload into ClanSummary records."""
    if not isinstance(payload, list):
        raise FwaStatsError(f"Expected a JSON list from fwastats, got {type(payload).__name__}.")

    clans: list[ClanSummary] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        th_counts = {
            label: (_coerce_int(item.get(json_key)) or 0)
            for label, json_key in TH_COUNT_KEYS
        }
        est = _coerce_int(item.get("estimatedWeight"))
        clans.append(
            ClanSummary(
                tag=str(item.get("tag") or "").strip(),
                name=str(item.get("name") or "Unknown").strip(),
                estimated_weight=est if est is not None and est > 0 else None,
                weight_submit_date=str(item.get("weightSubmitDate") or "").strip() or None,
                th_counts=th_counts,
            )
        )
    return clans


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
        payload = await self._get_json(url, context=normalized)
        return parse_member_weights(payload)

    async def fetch_war_members(self, clan_tag: str, *, war_no: int = 1) -> list[MemberWeight]:
        """Fetch war roster members for a clan from fwastats.com/Clan/<TAG>/WarMembers.json."""
        normalized = normalize_tag(clan_tag)
        url = f"{FWASTATS_BASE_URL}/Clan/{normalized.lstrip('#')}/WarMembers.json?warNo={war_no}"
        payload = await self._get_json(url, context=f"{normalized} warNo={war_no}")
        return parse_war_members(payload)

    async def fetch_all_clans(self) -> list[ClanSummary]:
        """Fetch all FWA clan summaries from fwastats.com/Clans.json."""
        url = f"{FWASTATS_BASE_URL}/Clans.json"
        payload = await self._get_json(url, context="Clans.json")
        return parse_clan_summaries(payload)

    async def _get_json(self, url: str, *, context: str) -> Any:
        await self.start()
        assert self._session is not None

        try:
            async with self._session.get(url) as response:
                if response.status != 200:
                    raise FwaStatsError(f"fwastats.com returned HTTP {response.status} for {context}.")
                return await response.json(content_type=None)
        except FwaStatsError:
            raise
        except aiohttp.ClientError as exc:
            raise FwaStatsError(f"Failed to reach fwastats.com: {exc}") from exc
        except ValueError as exc:
            raise FwaStatsError("fwastats.com returned invalid JSON.") from exc
