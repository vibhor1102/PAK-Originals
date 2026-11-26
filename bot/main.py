from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .commands.weights import build_weights_command
from .config import AppConfig
from .fwastats import FwaStatsClient

LOGGER = logging.getLogger(__name__)


class PakOriginalsBot(commands.Bot):
    """Discord bot for The Originals clan."""

    def __init__(self, config: AppConfig) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = config
        self.fwastats = FwaStatsClient()

    async def setup_hook(self) -> None:
        self.tree.add_command(build_weights_command())

        if self.config.discord_guild_id is not None:
            guild = discord.Object(id=self.config.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            LOGGER.info("Synced %d command(s) to guild %s.", len(synced), self.config.discord_guild_id)
        else:
            synced = await self.tree.sync()
            LOGGER.info("Synced %d global command(s).", len(synced))

    async def on_ready(self) -> None:
        if self.user is not None:
            LOGGER.info("Logged in as %s (%s).", self.user, self.user.id)

    async def close(self) -> None:
        await self.fwastats.close()
        await super().close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = AppConfig.from_env()
    bot = PakOriginalsBot(config)
    bot.run(config.discord_token, log_handler=None)
