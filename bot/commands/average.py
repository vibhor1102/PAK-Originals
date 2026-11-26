from __future__ import annotations

import asyncio
from collections import Counter
import statistics
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ..config import DEFAULT_CLAN_NAME, DEFAULT_CLAN_TAG
from ..fwastats import ClanSummary, FwaStatsError, MemberWeight, normalize_tag, weight_to_th_band

if TYPE_CHECKING:
    from ..main import PakOriginalsBot

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
    clan_name: str = DEFAULT_CLAN_NAME,
    clan_tag: str = DEFAULT_CLAN_TAG,
) -> discord.Embed:
    """Build an embed comparing FWA-wide mean/median clan weights and TH bands to The Originals."""
    weighed_clans = [c for c in clans if c.estimated_weight is not None]
    if not weighed_clans:
        raise FwaStatsError("fwastats.com returned no clans with estimated weights.")

    fwa_weights = [c.estimated_weight * 1000 for c in weighed_clans if c.estimated_weight is not None]
    mean_weight = round(statistics.mean(fwa_weights))
    median_weight = round(statistics.median(fwa_weights))
    min_weight = min(fwa_weights)
    max_weight = max(fwa_weights)

    normalized_target = normalize_tag(clan_tag)
    clan_summary = next(
        (c for c in clans if c.tag and normalize_tag(c.tag) == normalized_target),
        None,
    )

    in_war = [m for m in members if m.in_war is True]
    active_roster = in_war if in_war else members
    roster_weight = sum(m.weight for m in active_roster if m.weight is not None and m.weight > 0)
    est_weight = (
        clan_summary.estimated_weight * 1000
        if clan_summary is not None and clan_summary.estimated_weight is not None
        else None
    )
    compare_weight = est_weight if est_weight is not None else roster_weight

    originals_bands = _member_band_counts(active_roster)

    rows: list[str] = ["TH    | FWA Mean | FWA Med | Originals"]
    for key in DISPLAY_TH_KEYS:
        vals = [c.th_counts.get(key, 0) for c in weighed_clans]
        fwa_mean_th = statistics.mean(vals)
        fwa_med_th = statistics.median(vals)
        orig_count = originals_bands.get(key, 0)
        if fwa_mean_th < 0.05 and fwa_med_th == 0 and orig_count == 0:
            continue
        rows.append(f"{key:<5} | {fwa_mean_th:>8.1f} | {fwa_med_th:>7.1f} | {orig_count:>9}")

    embed = discord.Embed(
        title=f"FWA Clan Average vs {clan_name} ({clan_tag})",
        description=f"```\n" + "\n".join(rows) + "\n```",
        color=discord.Color.teal(),
    )
    embed.add_field(
        name=f"FWA Weight ({len(weighed_clans)}/{len(clans)} clans)",
        value=(
            f"Mean: **{mean_weight:,}**\n"
            f"Median: **{median_weight:,}**\n"
            f"Range: {min_weight:,} – {max_weight:,}"
        ),
        inline=True,
    )

    originals_lines = [f"In-War Weight: **{roster_weight:,}** ({len(active_roster)} members)"]
    if est_weight is not None:
        originals_lines.append(f"FWA Est. Weight: **{est_weight:,}**")
    originals_lines.append(
        f"vs Mean: **{compare_weight - mean_weight:+,}**\n"
        f"vs Median: **{compare_weight - median_weight:+,}**"
    )
    embed.add_field(
        name=f"{clan_name}",
        value="\n".join(originals_lines),
        inline=True,
    )
    embed.set_footer(
        text="Source: fwastats.com (Clans.json + Members.json) • Originals column uses 10k weight bands"
    )
    return embed


def build_average_command() -> app_commands.Command:
    @app_commands.command(
        name="average",
        description=f"Compare FWA mean/median clan weights and TH bands against {DEFAULT_CLAN_NAME}.",
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

        embed = format_average_embed(clans, members)
        await interaction.followup.send(embed=embed)

    return average_command
