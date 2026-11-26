from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ..config import DEFAULT_CLAN_NAME, DEFAULT_CLAN_TAG
from ..fwastats import FwaStatsError, MemberWeight, weight_to_th_band

if TYPE_CHECKING:
    from ..main import PakOriginalsBot

MAX_EMBED_DESCRIPTION = 4096


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


def summarize_weight_bands(members: list[MemberWeight]) -> Counter[int]:
    """Count members in each 10k war-weight TH band."""
    counts: Counter[int] = Counter()
    for member in members:
        band = weight_to_th_band(member.weight)
        if band is not None:
            counts[band] += 1
    return counts


def format_weights_embed(
    members: list[MemberWeight],
    *,
    clan_name: str = DEFAULT_CLAN_NAME,
    clan_tag: str = DEFAULT_CLAN_TAG,
) -> discord.Embed:
    """Build a Discord embed displaying clan member war weights categorized by TH weight band."""
    sorted_members = sort_members_by_weight(members)
    weighed = [m for m in sorted_members if m.weight is not None and m.weight > 0]
    in_war = [m for m in sorted_members if m.in_war is True]
    in_war_weight = sum(m.weight for m in in_war if m.weight is not None and m.weight > 0)
    total_weight = sum(m.weight for m in weighed if m.weight is not None)

    band_counts = summarize_weight_bands(in_war if in_war else sorted_members)
    band_summary = " • ".join(
        f"TH{th}: {band_counts[th]}" for th in sorted(band_counts, reverse=True)
    ) or "None"

    lines: list[str] = []
    for idx, member in enumerate(sorted_members, start=1):
        war_mark = "*" if member.in_war else " "
        band_th = weight_to_th_band(member.weight)
        band_label = f"TH{band_th:<2}" if band_th is not None else "TH??"
        weight_label = f"{member.weight:>7,}" if member.weight is not None else "    N/A"
        actual_note = (
            f" (TH{member.town_hall})"
            if member.town_hall is not None and band_th is not None and member.town_hall != band_th
            else ""
        )
        lines.append(f"{idx:>2}.{war_mark} {band_label} | {weight_label} | {member.name}{actual_note}")

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
    embed.add_field(name="Members", value=f"{len(sorted_members)} ({len(in_war)} in war)", inline=True)
    embed.add_field(name="In-War Weight", value=f"{in_war_weight:,}", inline=True)
    embed.add_field(name="Total Roster Weight", value=f"{total_weight:,}", inline=True)
    embed.add_field(
        name="Weight-Band THs (In War)" if in_war else "Weight-Band THs",
        value=band_summary,
        inline=False,
    )
    embed.set_footer(text="Source: fwastats.com • * = In War • Bands: (170k,180k]=TH18, (180k,190k]=TH19")
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

        embed = format_weights_embed(members)
        await interaction.followup.send(embed=embed)

    return weights_command
