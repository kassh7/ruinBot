import asyncio
import random
import re
import time
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import discord
from discord.ext import commands


class LinkFixerView(discord.ui.View):
    def __init__(self, cog, original_message: discord.Message, fixed_links: list[str], delay: int = 5):
        super().__init__(timeout=60)
        self.cog = cog
        self.original_message = original_message
        self.fixed_links = fixed_links
        self.delay = delay
        self.suppression_cancelled = False
        self.bot_message: discord.Message | None = None

        self._suppress_task = asyncio.create_task(self.delayed_suppress())
        # Remove refresh button if all links are vxreddit
        if all("vxreddit.com" in link for link in self.fixed_links):
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.custom_id == "refresh_embed":
                    self.remove_item(item)
                    break

    async def delayed_suppress(self):
        try:
            await asyncio.sleep(self.delay)

            if self.suppression_cancelled:
                return

            await self.original_message.edit(suppress=True)

            # Properly remove the "Keep original" button
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.custom_id == "keep_original":
                    self.remove_item(item)
                    break

            if self.bot_message:
                await self.bot_message.edit(view=self)

        except discord.Forbidden:
            print(
                f"baj van: Nincs jogom elrejteni az embedet itt: "
                f"{getattr(self.original_message.channel, 'name', 'unknown')}"
            )
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"baj van delayed suppress közben: {e}")

    def build_message_content(self) -> str:
        return (
            f"🗣️ **{self.original_message.author.display_name}** küldte:\n"
            + "\n".join(self.fixed_links)
        )

    @staticmethod
    def add_cache_buster(url: str) -> str:
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query))
        query["_rb"] = str(int(time.time() * 1000))  # Discord sees a "new" URL
        new_query = urlencode(query)
        return urlunparse(parsed._replace(query=new_query))

    @discord.ui.button(
        label="Keep original",
        style=discord.ButtonStyle.secondary,
        custom_id="keep_original"
    )
    async def keep_original(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        self.suppression_cancelled = True

        if self._suppress_task and not self._suppress_task.done():
            self._suppress_task.cancel()

        try:
            await interaction.response.defer()
        except Exception:
            pass

        try:
            if self.bot_message:
                await self.bot_message.delete()
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"baj van keep_original delete közben: {e}")

        self.stop()

    @discord.ui.button(
        label="Refresh embed",
        style=discord.ButtonStyle.primary,
        custom_id="refresh_embed"
    )
    async def refresh_embed(
            self,
            interaction: discord.Interaction,
            button: discord.ui.Button
    ):
        refreshed_links = []

        for link in self.fixed_links:
            if "vxreddit.com" in link:
                refreshed_links.append(link)
            else:
                refreshed_links.append(self.add_cache_buster(link))

        self.fixed_links = refreshed_links

        try:
            await interaction.response.edit_message(
                content=self.build_message_content(),
                view=self
            )
        except Exception as e:
            print(f"baj van refresh közben: {e}")

    async def on_timeout(self):
        if self._suppress_task and not self._suppress_task.done():
            # Let the suppress still happen naturally if it's already pending.
            pass

        for item in self.children:
            item.disabled = True

        try:
            if self.bot_message:
                await self.bot_message.edit(view=self)
        except Exception:
            pass


class LinkFixer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Regex is magic! It finds the links even if there is other text in the message!
        self.x_pattern = re.compile(r'https?://(?:www\.)?(?:x|twitter)\.com/([^\s]+)')
        self.ig_pattern = re.compile(r'https?://(?:www\.)?instagram\.com/([^\s]+)')
        self.reddit_pattern = re.compile(r'https?://(?:www\.)?reddit\.com/([^\s]+)')

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ne válaszoljon saját magának vagy más botoknak!
        if message.author.bot:
            return

        fixed_links = []

        # --- TWITTER / X FIX ---
        x_domains = [
            "fxtwitter.com",
            "vxtwitter.com",
            "fixupx.com",
            "girlcockx.com",
            "hitlerx.com",
            "cunnyx.com",
            "stupidpenisx.com"
        ]
        for match in self.x_pattern.finditer(message.content):
            domain = random.choice(x_domains)
            fixed_links.append(f"https://{domain}/{match.group(1)}")

        # --- INSTAGRAM FIX ---
        for match in self.ig_pattern.finditer(message.content):
            fixed_links.append(f"https://kkinstagram.com/{match.group(1)}")

        # --- REDDIT FIX ---
        for match in self.reddit_pattern.finditer(message.content):
            fixed_links.append(f"https://vxreddit.com/{match.group(1)}")

        if fixed_links:
            try:
                view = LinkFixerView(self, message, fixed_links, delay=5)

                final_message = view.build_message_content()
                bot_message = await message.channel.send(final_message, view=view)
                view.bot_message = bot_message

            except discord.Forbidden:
                print(f"baj van: Nincs jogom írni ide: {message.channel.name}")
            except Exception as e:
                print(f"baj van: {e}")


async def setup(bot):
    await bot.add_cog(LinkFixer(bot))