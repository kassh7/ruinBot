import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp
import discord
from discord.ext import commands


STEAM_APP_URL = re.compile(
    r"(?:https?://)?(?:store\.)?steampowered\.com/app/(\d+)", re.IGNORECASE
)
STEAM_APP_ID = re.compile(r"^\d+$")
DATE_FORMATS = ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y")


class SteamLookupError(Exception):
    pass


@dataclass(frozen=True)
class SteamGame:
    app_id: int
    name: str
    description: str
    image_url: str
    release_at: datetime

    @property
    def store_url(self) -> str:
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
        super().__init__(timeout=60)
        self.cog = cog
        self.game = game
        self.requester_id = requester_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
        return False

    @discord.ui.button(label="Create event", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
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


class SteamRelease(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
        release_at = parse_release_date(raw_date)
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

    async def create_event(self, guild: Optional[discord.Guild], game: SteamGame):
        if guild is None:
            raise SteamLookupError("This command can only be used in a server.")
        if game.release_at <= datetime.now(timezone.utc):
            raise SteamLookupError("That game's release date has already passed.")

        image = await self.get_image(game.image_url)
        description = game.description.strip() or "Steam release"
        description = f"{description[:880]}\n\n{game.store_url}"
        return await guild.create_scheduled_event(
            name=f"{game.name} release"[:100],
            description=description[:1000],
            start_time=game.release_at,
            end_time=game.release_at + timedelta(hours=1),
            entity_type=discord.EntityType.external,
            privacy_level=discord.PrivacyLevel.guild_only,
            location="Steam",
            image=image,
            reason="Game release event requested through ruinBot",
        )

    @commands.hybrid_command(name="release", description="Create an event for a Steam game release")
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
            if app_id is None:
                app_id = await self.search_app_id(game)
            result = await self.get_game(app_id)
        except (aiohttp.ClientError, SteamLookupError) as exc:
            await ctx.send(f"Could not look up that game: {exc}", ephemeral=True)
            return

        if is_name_search:
            embed = discord.Embed(
                title=result.name,
                url=result.store_url,
                description=result.description[:1000],
                colour=discord.Colour.blue(),
            )
            embed.add_field(name="Release date", value=discord.utils.format_dt(result.release_at, "D"))
            if result.image_url:
                embed.set_image(url=result.image_url)
            await ctx.send(
                "Is this the game you meant?",
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
