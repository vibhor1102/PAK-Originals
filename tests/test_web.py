from __future__ import annotations

import unittest

from aiohttp.test_utils import AioHTTPTestCase

from bot.config import AppConfig
from bot.main import PakOriginalsBot, create_web_app


class WebHealthRoutesTests(AioHTTPTestCase):
    async def get_application(self):
        bot = PakOriginalsBot(AppConfig(discord_token="test-token"))
        return create_web_app(bot)

    async def test_index_get_and_head(self) -> None:
        resp = await self.client.get("/")
        self.assertEqual(resp.status, 200)
        text = await resp.text()
        self.assertIn("awake", text)

        head_resp = await self.client.head("/")
        self.assertEqual(head_resp.status, 200)

    async def test_health_endpoint(self) -> None:
        resp = await self.client.get("/health")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("discord_ready", data)
        self.assertIn("latency_ms", data)


if __name__ == "__main__":
    unittest.main()
