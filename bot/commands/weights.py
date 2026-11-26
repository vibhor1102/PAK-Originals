from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ..config import DEFAULT_CLAN_NAME, DEFAULT_CLAN_TAG
from ..fwastats import FwaStatsClient, FwaStatsError, MemberWeight, normalize_tag, weight_to_th_band

if TYPE_CHECKING:
    from ..main import PakOriginalsBot

LOGGER = logging.getLogger(__name__)
MAX_EMBED_DESCRIPTION = 4096
TARGET_WAR_SIZE = 50


@dataclass(frozen=True, slots=True)
class RosterEntry:
    """Member entry in the projected war roster."""

    member: MemberWeight
    provisional: bool = False


def sort_members_by_weight(members: list[MemberWeight]) -> list[MemberWeight]:
    """Sort members by weight descending, then town hall descending, then rank ascending."""
    return sorted(
        members,
        key=lambda m: (
            -(m.weight if m.weight is not None else -1),
            -(m.town_hall if m.town_hall is not None else -1),
            m.rank if m.rank is not None else 999,
            m.name.lower(),
        ),
    )


def build_provisional_roster(
    current_members: list[MemberWeight],
    departed_members: list[MemberWeight] | None = None,
    *,
    target_size: int = TARGET_WAR_SIZE,
) -> tuple[list[RosterEntry], int, int]:
    """Build up to `target_size` war roster entries, filling missing slots with departed members."""
    current_sorted = sort_members_by_weight(current_members)
    entries: list[RosterEntry] = [
        RosterEntry(m, provisional=False) for m in current_sorted[:target_size]
    ]

    if len(entries) < target_size and departed_members:
        needed = target_size - len(entries)
        entries.extend(RosterEntry(m, provisional=True) for m in departed_members[:needed])

    entries.sort(
        key=lambda e: (
            -(e.member.weight if e.member.weight is not None else -1),
            -(e.member.town_hall if e.member.town_hall is not None else -1),
            e.member.rank if e.member.rank is not None else 999,
            e.member.name.lower(),
        )
    )
    current_count = sum(1 for e in entries if not e.provisional)
    provisional_count = sum(1 for e in entries if e.provisional)
    return entries, current_count, provisional_count


async def fetch_projected_roster(
    fwastats: FwaStatsClient,
    clan_tag: str,
    current_members: list[MemberWeight],
    *,
    target_size: int = TARGET_WAR_SIZE,
) -> tuple[list[RosterEntry], int, int, list[MemberWeight]]:
    """Fill any shortfall below `target_size` using previous-war members from WarMembers.json?warNo=1."""
    departed: list[MemberWeight] = []
    if len(current_members) < target_size:
        current_tags = {normalize_tag(m.tag) for m in current_members if m.tag.strip()}
        try:
            prev_war_members = await fwastats.fetch_war_members(clan_tag, war_no=1)
            departed = [
                m
                for m in sort_members_by_weight(prev_war_members)
                if m.tag.strip() and normalize_tag(m.tag) not in current_tags
            ]
        except FwaStatsError as exc:
            LOGGER.warning("Could not fetch WarMembers.json?warNo=1 for %s: %s", clan_tag, exc)

    entries, current_count, provisional_count = build_provisional_roster(
        current_members, departed, target_size=target_size
    )
    return entries, current_count, provisional_count, departed


def summarize_weight_bands(members: list[MemberWeight]) -> Counter[int]:
    """Count members in each 10k war-weight TH band."""
    counts: Counter[int] = Counter()
    for member in members:
        band = weight_to_th_band(member.weight)
        if band is not None:
            counts[band] += 1
    return counts


def format_weights_embed(
    current_members: list[MemberWeight],
    *,
    departed_members: list[MemberWeight] | None = None,
    clan_name: str = DEFAULT_CLAN_NAME,
    clan_tag: str = DEFAULT_CLAN_TAG,
) -> discord.Embed:
    """Build a Discord embed displaying projected 50-member war weights by TH weight band."""
    entries, current_count, provisional_count = build_provisional_roster(
        current_members, departed_members, target_size=TARGET_WAR_SIZE
    )
    projected_members = [e.member for e in entries]
    projected_weight = sum(
        m.weight for m in projected_members if m.weight is not None and m.weight > 0
    )
    current_weight = sum(
        e.member.weight
        for e in entries
        if not e.provisional and e.member.weight is not None and e.member.weight > 0
    )

    band_counts = summarize_weight_bands(projected_members)
    band_summary = " • ".join(
        f"TH{th}: {band_counts[th]}" for th in sorted(band_counts, reverse=True)
    ) or "None"

    lines: list[str] = []
    for idx, entry in enumerate(entries, start=1):
        member = entry.member
        mark = "~" if entry.provisional else " "
        band_th = weight_to_th_band(member.weight)
        band_label = f"TH{band_th:<2}" if band_th is not None else "TH??"
        weight_label = f"{member.weight:>7,}" if member.weight is not None else "    N/A"
        actual_note = (
            f" (TH{member.town_hall})"
            if member.town_hall is not None and band_th is not None and member.town_hall != band_th
            else ""
        )
        lines.append(f"{idx:>2}.{mark} {band_label} | {weight_label} | {member.name}{actual_note}")

    body = "\n".join(lines) if lines else "No members found."
    code_block = f"```\n{body}\n```"
    if len(code_block) > MAX_EMBED_DESCRIPTION:
        truncated_lines: list[str] = []
        current_len = 8
        suffix = "\n... (truncated)"
        for line in lines:
            if current_len + len(line) + 1 + len(suffix) > MAX_EMBED_DESCRIPTION:
                break
            truncated_lines.append(line)
            current_len += len(line) + 1
        body = "\n".join(truncated_lines) + suffix
        code_block = f"```\n{body}\n```"

    embed = discord.Embed(
        title=f"{clan_name} ({clan_tag}) — War Weights",
        description=code_block,
        color=discord.Color.blurple(),
    )
    member_summary = f"{len(entries)}/{TARGET_WAR_SIZE} ({current_count} current"
    if provisional_count:
        member_summary += f", {provisional_count} prov."
    member_summary += ")"

    embed.add_field(name="Roster", value=member_summary, inline=True)
    embed.add_field(name="Current Weight", value=f"{current_weight:,}", inline=True)
    embed.add_field(
        name=f"Projected Weight ({len(entries)}/{TARGET_WAR_SIZE})",
        value=f"{projected_weight:,}",
        inline=True,
    )
    embed.add_field(name="Weight-Band THs", value=band_summary, inline=False)
    embed.set_footer(
        text="Source: fwastats.com • ~ = Provisional (last war) • Bands: (170k,180k]=TH18, (180k,190k]=TH19"
    )
    return embed


def build_weights_command() -> app_commands.Command:
    @app_commands.command(
        name="weights",
        description=f"Show war weights for {DEFAULT_CLAN_NAME} ({DEFAULT_CLAN_TAG}) from fwastats.",
    )
    async def weights_command(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        bot: PakOriginalsBot = interaction.client  # type: ignore[assignment]

        try:
            members = await bot.fwastats.fetch_clan_members(DEFAULT_CLAN_TAG)
        except FwaStatsError as exc:
            await interaction.followup.send(f"Could not fetch war weights: {exc}", ephemeral=True)
            return

        if not members:
            await interaction.followup.send(
                f"No members returned by fwastats.com for {DEFAULT_CLAN_NAME} (`{DEFAULT_CLAN_TAG}`).",
                ephemeral=True,
            )
            return

        _, _, _, departed = await fetch_projected_roster(bot.fwastats, DEFAULT_CLAN_TAG, members)
        embed = format_weights_embed(members, departed_members=departed)
        await interaction.followup.send(embed=embed)

    return weights_command
