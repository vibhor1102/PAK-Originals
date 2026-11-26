from __future__ import annotations

import asyncio
import logging
import math

import discord
from aiohttp import web
from discord.ext import commands

from .commands.average import build_average_command
from .commands.weights import build_weights_command
from .config import AppConfig
from .database import Database
from .fwastats import FwaStatsClient

LOGGER = logging.getLogger(__name__)


class PakOriginalsBot(commands.Bot):
    """Discord bot for The Originals clan."""

    def __init__(self, config: AppConfig, db: Database | None = None) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = config
        self.db = db if db is not None else Database(None)
        self.fwastats = FwaStatsClient()

    async def setup_hook(self) -> None:
        self.tree.add_command(build_weights_command())
        self.tree.add_command(build_average_command())

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


def create_web_app(bot: PakOriginalsBot) -> web.Application:
    """Create the HTTP app used by Render health checks and UptimeRobot."""
    app = web.Application()

    async def index(_request: web.Request) -> web.Response:
        return web.Response(text="PAK-Originals bot is awake.")

    async def health(_request: web.Request) -> web.Response:
        latency = bot.latency
        latency_ms = round(latency * 1000) if latency is not None and math.isfinite(latency) else None
        return web.json_response(
            {
                "status": "ok",
                "discord_ready": bot.is_ready(),
                "database_connected": bot.db.connected,
                "latency_ms": latency_ms,
            }
        )

    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    return app


async def start_web_server(bot: PakOriginalsBot, port: int) -> web.AppRunner:
    runner = web.AppRunner(create_web_app(bot))
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    LOGGER.info("Health server listening on port %d.", port)
    return runner


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = AppConfig.from_env()
    db = Database(config.database_url)
    await db.connect()
    bot = PakOriginalsBot(config, db=db)
    runner = await start_web_server(bot, config.port)
    try:
        await bot.start(config.discord_token)
    finally:
        await bot.close()
        await db.close()
        await runner.cleanup()


def main() -> None:
    asyncio.run(run())
