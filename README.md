# PAK-Originals Bot

Discord bot for **The Originals** (`#2LCUU9YYU`).

## Setup

1. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set `DISCORD_TOKEN` (and optionally `DISCORD_GUILD_ID` for fast guild command syncing).
3. Run the bot:
   ```bash
   python -m bot
   ```

## Commands

- `/weights` — Fetches current member war weights for **The Originals** (`#2LCUU9YYU`) from `fwastats.com` and categorizes players by 10k TH weight bands (`(170k, 180k]` = TH18, `(180k, 190k]` = TH19, etc.).
- `/average` — Shows FWA-wide median clan weight and TH composition from `fwastats.com/Clans.json` alongside **The Originals**.
