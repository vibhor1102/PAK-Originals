from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

REPO_ROOT = Path(__file__).resolve().parents[1]
DOTENV_PATH = REPO_ROOT / ".env"

DEFAULT_CLAN_TAG = "#2LCUU9YYU"
DEFAULT_CLAN_NAME = "The Originals"


def load_dotenv(path: Path = DOTENV_PATH) -> None:
    """Load simple KEY=VALUE pairs from .env without overriding existing env vars."""
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Application configuration loaded from environment variables."""

    discord_token: str
    discord_guild_id: int | None = None

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()

        discord_token = os.getenv("DISCORD_TOKEN", "").strip()
        if not discord_token:
            raise RuntimeError("DISCORD_TOKEN environment variable is required.")

        raw_guild_id = os.getenv("DISCORD_GUILD_ID", "").strip()
        discord_guild_id: int | None = None
        if raw_guild_id:
            try:
                discord_guild_id = int(raw_guild_id)
            except ValueError as exc:
                raise RuntimeError("DISCORD_GUILD_ID must be a valid integer.") from exc

        return cls(
            discord_token=discord_token,
            discord_guild_id=discord_guild_id,
        )
