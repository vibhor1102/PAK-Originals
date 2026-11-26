from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
import statistics
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ..config import DEFAULT_CLAN_NAME, DEFAULT_CLAN_TAG
from ..fwastats import ClanSummary, FwaStatsError, MemberWeight, normalize_tag, weight_to_th_band
from .weights import TARGET_WAR_SIZE, build_provisional_roster, fetch_projected_roster

if TYPE_CHECKING:
    from ..main import PakOriginalsBot

DEFAULT_FRESHNESS_DAYS = 7

DISPLAY_TH_KEYS: tuple[str, ...] = (
    "TH19",
    "TH18",
    "TH17",
    "TH16",
    "TH15",
    "TH14",
    "TH13",
    "TH12",
    "TH11",
    "TH10",
    "TH9",
    "TH8",
    "TH<=7",
)


def _parse_iso_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def filter_recent_weighed_clans(
    clans: list[ClanSummary],
    *,
    days: int = DEFAULT_FRESHNESS_DAYS,
    now: datetime | None = None,
) -> list[ClanSummary]:
    """Return clans with an estimated weight updated within the last `days` days."""
    reference = now if now is not None else datetime.now(timezone.utc)
    cutoff = reference - timedelta(days=days)
    recent: list[ClanSummary] = []
    for clan in clans:
        if clan.estimated_weight is None:
            continue
        submitted = _parse_iso_utc(clan.weight_submit_date)
        if submitted is not None and submitted >= cutoff:
            recent.append(clan)
    return recent


def adjust_medians_to_total(
    th_series: dict[str, list[int]],
    *,
    target_total: int = TARGET_WAR_SIZE,
) -> dict[str, int]:
    """Compute per-TH integer medians and adjust along (mean - count) skew so total == target_total."""
    counts: dict[str, int] = {}
    means: dict[str, float] = {}
    for key, vals in th_series.items():
        if not vals:
            counts[key] = 0
            means[key] = 0.0
            continue
        counts[key] = round(statistics.median(vals))
        means[key] = statistics.mean(vals)

    current_total = sum(counts.values())
    if current_total == target_total or not counts:
        return counts

    while current_total < target_total:
        candidates = [k for k in counts if means[k] > 0] or list(counts.keys())
        best = max(candidates, key=lambda k: (means[k] - counts[k], means[k]))
        counts[best] += 1
        current_total += 1

    while current_total > target_total:
        candidates = [k for k in counts if counts[k] > 0]
        if not candidates:
            break
        best = min(candidates, key=lambda k: (means[k] - counts[k], -counts[k]))
        counts[best] -= 1
        current_total -= 1

    return counts


def _member_band_counts(members: list[MemberWeight]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for member in members:
        band = weight_to_th_band(member.weight)
        if band is None:
            continue
        key = f"TH{band}" if band >= 8 else "TH<=7"
        counts[key] += 1
    return counts


def format_average_embed(
    clans: list[ClanSummary],
    members: list[MemberWeight],
    *,
    departed_members: list[MemberWeight] | None = None,
    clan_name: str = DEFAULT_CLAN_NAME,
    clan_tag: str = DEFAULT_CLAN_TAG,
    days: int = DEFAULT_FRESHNESS_DAYS,
    now: datetime | None = None,
) -> discord.Embed:
    """Build an embed comparing 50-adjusted FWA median THs and weight to The Originals."""
    recent_clans = filter_recent_weighed_clans(clans, days=days, now=now)
    if not recent_clans:
        raise FwaStatsError(f"fwastats.com returned no clans updated within the last {days} days.")

    fwa_weights = [c.estimated_weight * 1000 for c in recent_clans if c.estimated_weight is not None]
    median_weight = round(statistics.median(fwa_weights))
    min_weight = min(fwa_weights)
    max_weight = max(fwa_weights)

    th_series = {key: [c.th_counts.get(key, 0) for c in recent_clans] for key in DISPLAY_TH_KEYS}
    adjusted_medians = adjust_medians_to_total(th_series, target_total=TARGET_WAR_SIZE)

    normalized_target = normalize_tag(clan_tag)
    clan_summary = next(
        (c for c in clans if c.tag and normalize_tag(c.tag) == normalized_target),
        None,
    )

    entries, current_count, provisional_count = build_provisional_roster(
        members, departed_members, target_size=TARGET_WAR_SIZE
    )
    projected_members = [e.member for e in entries]
    projected_weight = sum(
        m.weight for m in projected_members if m.weight is not None and m.weight > 0
    )
    est_weight = (
        clan_summary.estimated_weight * 1000
        if clan_summary is not None and clan_summary.estimated_weight is not None
        else None
    )
    compare_weight = est_weight if est_weight is not None else projected_weight

    originals_bands = _member_band_counts(projected_members)

    rows: list[str] = ["TH    | FWA Med | Originals"]
    for key in DISPLAY_TH_KEYS:
        fwa_med_th = adjusted_medians[key]
        orig_count = originals_bands.get(key, 0)
        if fwa_med_th == 0 and orig_count == 0:
            continue
        rows.append(f"{key:<5} | {fwa_med_th:>7} | {orig_count:>9}")
    rows.append("------+---------+----------")
    rows.append(f"Total | {sum(adjusted_medians.values()):>7} | {sum(originals_bands.values()):>9}")

    embed = discord.Embed(
        title=f"FWA Clan Median (Last {days}d) vs {clan_name} ({clan_tag})",
        description="```\n" + "\n".join(rows) + "\n```",
        color=discord.Color.teal(),
    )
    embed.add_field(
        name=f"FWA Weight ({len(recent_clans)}/{len(clans)} clans, {days}d)",
        value=(
            f"Median: **{median_weight:,}**\n"
            f"Range: {min_weight:,} – {max_weight:,}"
        ),
        inline=True,
    )

    roster_note = f"{current_count} current"
    if provisional_count:
        roster_note += f" + {provisional_count} prov."
    originals_lines = [
        f"Projected ({len(entries)}/{TARGET_WAR_SIZE}): **{projected_weight:,}** ({roster_note})"
    ]
    if est_weight is not None:
        originals_lines.append(f"FWA Est. Weight: **{est_weight:,}**")
    originals_lines.append(f"vs Median: **{compare_weight - median_weight:+,}**")
    embed.add_field(
        name=f"{clan_name}",
        value="\n".join(originals_lines),
        inline=True,
    )
    embed.set_footer(
        text=(
            f"Source: fwastats.com (last {days}d) • FWA Med adjusted to 50 by mean skew • "
            "Originals uses 10k bands"
        )
    )
    return embed


def build_average_command() -> app_commands.Command:
    @app_commands.command(
        name="average",
        description=f"Compare FWA median clan weight (last {DEFAULT_FRESHNESS_DAYS}d) against {DEFAULT_CLAN_NAME}.",
    )
    async def average_command(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        bot: PakOriginalsBot = interaction.client  # type: ignore[assignment]

        try:
            clans, members = await asyncio.gather(
                bot.fwastats.fetch_all_clans(),
                bot.fwastats.fetch_clan_members(DEFAULT_CLAN_TAG),
            )
        except FwaStatsError as exc:
            await interaction.followup.send(f"Could not fetch FWA averages: {exc}", ephemeral=True)
            return

        _, _, _, departed = await fetch_projected_roster(bot.fwastats, DEFAULT_CLAN_TAG, members)
        embed = format_average_embed(clans, members, departed_members=departed)
        await interaction.followup.send(embed=embed)

    return average_command
