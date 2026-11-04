# AGENTS.md — ruinBot

Hungarian Discord bot ("cirkadián adjusztment", not a real robot) built on discord.py 2.x.

## Project
- Entry point: `main.py` — creates `commands.Bot` (prefix `r!`, slash tree), opens SQLite at `usr/db.sqlite` in `on_ready`, loads every `cogs/*.py` as an extension, syncs slash commands to a hardcoded guild.
- Config: `.env` (see `.env-example`) — `DISCORD_TOKEN`, `CHANNEL` (required); `MORNING_HOUR/MINUTE`, `IMGFLIP_USER/PASS`, `BOT_FRIENDS`, `SPECIAL_DATE/ADJECTIVE` (optional). `CZ/CZ_SERV`, `KOZEL_*`, `MUSICBOT_*`, `VOCARD_IDS` are optional per-cog secrets read directly via `os.getenv`.
- Data/state lives in `usr/`: `db.sqlite` (soma tables), `markov/<channel_id>` text corpora, `markov_config.json`, `holidays.json` (API cache). This dir is volume-mounted in production.
- Static assets in `res/` (fonts, templates, namedays, demotivator JSON).

## Commands
- Run: `python main.py` (Python 3.12; 3.9+ per README). No test suite exists.
- Install deps: `pip install -r requirements.txt` (venv already at `.venv/`).
- Production: Dockerfile + `docker-compose.yml` (image `ghcr.io/kassh7/ruinbot`); CI at `.github/workflows/main.yml` builds & deploys to a VPS on push to `master`.
- Captchas are built from the markov dataset; the old `captcha-proxy/` sidecar is gone.

## Architecture
- `cogs/markov.py` — the core: per-channel Markov (markovify) training, bot-friend ping replies (`BOT_FRIENDS`), meme/motivator generation with Pillow. Largest cog (~1200 lines).
- `cogs/morning.py` — daily "morning" post: scrapes + generates day/month content, Hungarian namedays (`res/namedays_hu_mmdd.json`).
- `cogs/soma.py` — gambling/cooldown game; SQLite tables created in `main.py` (`soma`, `somacd`, `soma_tries`, `soma_wins`).
- `cogs/holidays.py` — Hungarian public holidays via `utils/holiday_cache.py` (caches API to `usr/holidays.json`, timezone `Europe/Budapest`).
- Others: `teletal` (TV schedule reminders), `steam_release` (Steam API release tracking + event scheduling), `rolepicker`, `kifogas` (excuses from `res/kifogasok.json`), `linkfixer` (X/IG/Reddit embed links + language suffix buttons), `cz`, `grok`, `vocardcleanup`, `util` (owner commands: `r!sync`, musicbot control).
- Each cog defines a `commands.Cog` subclass + `async def setup(bot)` at module bottom.

## Conventions
- Casual Hungarian tone in user-facing strings and comments; keep it.
- Logs to `ruinbot.log` + console, configured once in `main.py` (discord logger silenced to WARNING). Cogs use `logging.getLogger(__name__)`-style loggers, not prints for runtime info.
- No type-hint or lint tooling; follow the surrounding code.
- `allowed_mentions` is restrictive (roles/users/everyone off) at the bot level — don't re-enable broad mentions.
- Don't commit `.env`, `ruinbot.log`, or `usr/` state (see `.gitignore`).

## Notes
