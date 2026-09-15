import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp
import discord
import pytz
from bs4 import BeautifulSoup
from discord.ext import commands


STEAM_APP_URL = re.compile(
    r"(?:https?://)?(?:store\.)?steampowered\.com/app/(\d+)", re.IGNORECASE
)
STEAM_APP_ID = re.compile(r"^\d+$")
DATE_FORMATS = ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y")

# Manually maintained from the user's ARPG Timeline game-picker screenshot.
# Only a browser link is provided; the bot never requests Timeline data.
ARPG_TIMELINE_URL = "https://www.arpg-timeline.com/"
ARPG_TIMELINE_GAMES = (
    "Diablo II: Resurrected", "Diablo III", "Diablo IV", "Dwarven Realms",
    "Hero Siege", "Last Epoch", "Path of Exile", "Striving for Light",
    "Torchlight: Infinite", "Undecember", "Darkhaven", "Diablo V",
    "Emberville", "Gods, Death & Reapers", "No Rest For The Wicked",
    "Path of Exile 2", "Pathfinder: Abomination Vaults", "TARAE: The Unbound",
    "The Dark West", "Titan Quest II", "Wolcen 2",
)


def is_timeline_game(name: str) -> bool:
    def normalize(value):
        return re.sub(r"[^a-z0-9]", "", value.casefold())
    return normalize(name) in {normalize(game) for game in ARPG_TIMELINE_GAMES}


class SteamLookupError(Exception):
    pass


@dataclass(frozen=True)
class SteamGame:
    app_id: int
    name: str
    description: str
    image_url: str
    release_at: Optional[datetime]
    official_url: Optional[str] = None

    @property
    def store_url(self) -> str:
        if self.official_url:
            return self.official_url
        return f"https://store.steampowered.com/app/{self.app_id}/"


def app_id_from_query(query: str) -> Optional[int]:
    query = query.strip()
    match = STEAM_APP_URL.search(query)
    if match:
        return int(match.group(1))
    if STEAM_APP_ID.fullmatch(query):
        return int(query)
    return None


def parse_release_date(value: str) -> datetime:
    value = value.strip()
    for date_format in DATE_FORMATS:
        try:
            # Steam supplies a date but no time. Noon UTC avoids displaying the
            # event on the preceding day in negative UTC offsets.
            parsed = datetime.strptime(value, date_format)
            return parsed.replace(hour=12, tzinfo=timezone.utc)
        except ValueError:
            continue
    raise SteamLookupError(
        f"Steam does not list an exact release date (it says {value!r})."
    )


class ReleaseConfirmation(discord.ui.View):
    def __init__(self, cog: "SteamRelease", game: SteamGame, requester_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.game = game
        self.requester_id = requester_id
        self.submitting = False
        self.manual_date = (is_timeline_game(game.name) or game.release_at is None
                            or game.release_at <= datetime.now(timezone.utc))
        if self.manual_date:
            self.confirm.label = "Set event name and date"
        if is_timeline_game(game.name):
            self.add_item(discord.ui.Button(
                label="Check dates on ARPG Timeline",
                style=discord.ButtonStyle.link, url=ARPG_TIMELINE_URL))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
        return False

    @discord.ui.button(label="Create event", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.manual_date:
            await interaction.response.send_modal(CustomEventModal(self))
            return
        await interaction.response.defer(ephemeral=True)
        self.stop()
        try:
            event = await self.cog.create_event(interaction.guild, self.game)
        except (aiohttp.ClientError, discord.HTTPException, SteamLookupError) as exc:
            await interaction.edit_original_response(content=f"Could not create the event: {exc}", view=None)
            return
        await interaction.edit_original_response(
            content=f"Created **{event.name}** for {discord.utils.format_dt(self.game.release_at, 'D')}.",
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)


def parse_event_date(value: str) -> datetime:
    try:
        date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise SteamLookupError("Use YYYY-MM-DD HH:MM, e.g. 2027-01-15 20:00 (CET/CEST).")
    if date.tzinfo is None:
        try:
            date = pytz.timezone("Europe/Budapest").localize(date, is_dst=None)
        except pytz.NonExistentTimeError:
            raise SteamLookupError("That local time is skipped by the daylight-saving change. Choose another time.")
        except pytz.AmbiguousTimeError:
            raise SteamLookupError("That local time occurs twice when summer time ends. Choose another time or add +02:00 or +01:00.")
    if date <= datetime.now(timezone.utc):
        raise SteamLookupError("The event must start in the future.")
    return date


class CustomEventModal(discord.ui.Modal, title="Schedule a game event"):
    event_name = discord.ui.TextInput(label="Event name", max_length=100)
    event_date = discord.ui.TextInput(
        label="Start date/time (CET/CEST)",
        placeholder="2027-01-15 20:00", max_length=40,
    )

    def __init__(self, confirmation):
        super().__init__(timeout=300)
        self.confirmation = confirmation
        self.event_name.default = f"{confirmation.game.name} event"[:100]

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.confirmation.requester_id:
            await interaction.response.send_message("This form is not for you.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_events:
            await interaction.response.send_message("You need Manage Events permission.", ephemeral=True)
            return
        if self.confirmation.submitting or self.confirmation.is_finished():
            await interaction.response.send_message("This event was already submitted or expired.", ephemeral=True)
            return
        try:
            start = parse_event_date(self.event_date.value)
            name = self.event_name.value.strip()
            if not name:
                raise SteamLookupError("Enter an event name.")
        except SteamLookupError as exc:
            await interaction.response.send_message(
                f"{exc} Use the original button to try again.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        self.confirmation.submitting = True
        try:
            event = await self.confirmation.cog.create_event(
                interaction.guild, self.confirmation.game, event_name=name, start_time=start)
        except (aiohttp.ClientError, TimeoutError, discord.HTTPException, SteamLookupError) as exc:
            self.confirmation.submitting = False
            await interaction.followup.send(f"Could not create the event: {exc}", ephemeral=True)
            return
        self.confirmation.stop()
        await interaction.followup.send(
            f"Created **{event.name}** for {discord.utils.format_dt(start, 'F')}.", ephemeral=True)


class SteamRelease(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_nonsteam_game(self, query: str) -> Optional[SteamGame]:
        key = re.sub(r"[^a-z0-9]", "", query.lower())
        games = {
            "diablo3": ("Diablo III", "https://diablo3.blizzard.com/en-us/"),
            "diabloiii": ("Diablo III", "https://diablo3.blizzard.com/en-us/"),
            "d3": ("Diablo III", "https://diablo3.blizzard.com/en-us/"),
            "diablo2": ("Diablo II: Resurrected", "https://diablo2.blizzard.com/en-us/"),
            "diabloii": ("Diablo II: Resurrected", "https://diablo2.blizzard.com/en-us/"),
            "diablo2resurrected": ("Diablo II: Resurrected", "https://diablo2.blizzard.com/en-us/"),
            "diabloiiresurrected": ("Diablo II: Resurrected", "https://diablo2.blizzard.com/en-us/"),
            "d2r": ("Diablo II: Resurrected", "https://diablo2.blizzard.com/en-us/"),
        }
        if key not in games:
            return None
        name, url = games[key]
        description, image_url = f"Season or ladder reset for {name}.", ""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    soup = BeautifulSoup(await response.text(), "html.parser")
            image = soup.find("meta", property="og:image")
            summary = soup.find("meta", property="og:description")
            if image and image.get("content", "").startswith("https://"):
                image_url = image["content"]
            if summary and summary.get("content"):
                description = html.unescape(summary["content"])
        except (aiohttp.ClientError, TimeoutError):
            pass  # Manual scheduling remains available if the publisher is down.
        return SteamGame(0, name, description, image_url,
                         datetime(2000, 1, 1, tzinfo=timezone.utc), url)

    async def request_json(self, url: str, **params):
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {"User-Agent": "ruinBot Discord bot"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.json(content_type=None)

    async def search_app_id(self, name: str) -> int:
        payload = await self.request_json(
            "https://store.steampowered.com/api/storesearch/",
            term=name,
            l="english",
            cc="US",
        )
        items = payload.get("items") or []
        if not items:
            raise SteamLookupError(f"No Steam game matched {name!r}.")
        return int(items[0]["id"])

    async def get_game(self, app_id: int) -> SteamGame:
        payload = await self.request_json(
            "https://store.steampowered.com/api/appdetails",
            appids=app_id,
            l="english",
            cc="US",
        )
        result = payload.get(str(app_id), {})
        if not result.get("success") or not result.get("data"):
            raise SteamLookupError("Steam did not return details for that game.")

        data = result["data"]
        release = data.get("release_date") or {}
        raw_date = release.get("date", "Coming soon")
        try:
            release_at = parse_release_date(raw_date)
        except SteamLookupError:
            if not is_timeline_game(data.get("name", "")):
                raise
            release_at = None
        description = html.unescape(re.sub(r"<[^>]+>", "", data.get("short_description", "")))
        return SteamGame(
            app_id=app_id,
            name=data.get("name") or f"Steam app {app_id}",
            description=description,
            image_url=data.get("header_image", ""),
            release_at=release_at,
        )

    async def get_image(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                image = await response.read()
        # Discord's scheduled-event image limit is 10 MiB.
        return image if len(image) <= 10 * 1024 * 1024 else None

    async def create_event(self, guild: Optional[discord.Guild], game: SteamGame,
                           *, event_name: Optional[str] = None, start_time: Optional[datetime] = None):
        if guild is None:
            raise SteamLookupError("This command can only be used in a server.")
        start_time = start_time or game.release_at
        if start_time is None or start_time <= datetime.now(timezone.utc):
            raise SteamLookupError("The event must start in the future.")

        image = await self.get_image(game.image_url)
        description = game.description.strip() or "Steam release"
        description = f"{description[:880]}\n\n{game.store_url}"
        return await guild.create_scheduled_event(
            name=(event_name or f"{game.name} release")[:100],
            description=description[:1000],
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            entity_type=discord.EntityType.external,
            privacy_level=discord.PrivacyLevel.guild_only,
            location=game.store_url,
            image=image,
            reason="Game release event requested through ruinBot",
        )

    @commands.hybrid_command(name="release", description="Schedule a game release, season or ladder reset")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_events=True)
    @commands.bot_has_guild_permissions(manage_events=True)
    async def release(self, ctx: commands.Context, *, game: str):
        """Create a scheduled event from a Steam URL, app ID, or game name."""
        app_id = app_id_from_query(game)
        is_name_search = app_id is None

        if is_name_search and ctx.interaction is None:
            await ctx.reply("Game-name search needs a private confirmation. Please use `/release` instead.")
            return

        await ctx.defer(ephemeral=True)
        try:
            result = await self.get_nonsteam_game(game) if is_name_search else None
            if result is None and app_id is None:
                app_id = await self.search_app_id(game)
            if result is None:
                result = await self.get_game(app_id)
        except (aiohttp.ClientError, SteamLookupError) as exc:
            await ctx.send(f"Could not look up that game: {exc}", ephemeral=True)
            return

        timeline_game = is_timeline_game(result.name)
        already_released = result.release_at is not None and result.release_at <= datetime.now(timezone.utc)
        manual_date = timeline_game or already_released or result.release_at is None
        if manual_date and ctx.interaction is None:
            await ctx.reply("Use /release for this game to privately enter an event name and date.")
            return
        if is_name_search or manual_date:
            embed = discord.Embed(
                title=result.name,
                url=result.store_url,
                description=result.description[:1000],
                colour=discord.Colour.blue(),
            )
            if timeline_game:
                embed.add_field(
                    name="Check season / event dates",
                    value=f"[Open ARPG Timeline]({ARPG_TIMELINE_URL}), find **{result.name}**, "
                          "then use **Set event name and date** below. Enter your local CET/CEST time.",
                    inline=False,
                )
            if manual_date:
                embed.add_field(name="Schedule an event", value="Choose the event name and future date/time in the private form.")
            else:
                embed.add_field(name="Release date", value=discord.utils.format_dt(result.release_at, "D"))
            if result.image_url:
                embed.set_image(url=result.image_url)
            await ctx.send(
                ("Is this the game you meant? Set a name and date for your event."
                 if manual_date else "Is this the game you meant?"),
                embed=embed,
                view=ReleaseConfirmation(self, result, ctx.author.id),
                ephemeral=True,
            )
            return

        try:
            event = await self.create_event(ctx.guild, result)
        except (aiohttp.ClientError, discord.HTTPException, SteamLookupError) as exc:
            await ctx.send(f"Could not create the event: {exc}", ephemeral=True)
            return
        await ctx.send(
            f"Created **{event.name}** for {discord.utils.format_dt(result.release_at, 'D')}.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(SteamRelease(bot))
    # main.py performs a guild sync at startup; mirror global hybrid commands
    # into that guild before the sync so /release appears immediately.
    development_guild = discord.Object(id=232227916036046849)
    bot.tree.copy_global_to(guild=development_guild)
