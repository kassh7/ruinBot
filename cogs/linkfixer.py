import asyncio
import random
import re
import time
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import discord
from discord.ext import commands


X_EMBED_DOMAINS = (
    "fxtwitter.com",
    "vxtwitter.com",
    "fixupx.com",
    "girlcockx.com",
    "hitlerx.com",
    "cunnyx.com",
    "stupidpenisx.com",
)
INSTAGRAM_EMBED_DOMAINS = ("kkinstagram.com", "ddinstagram.com")
REDDIT_EMBED_DOMAINS = ("vxreddit.com", "rxddit.com")
EMBED_DOMAIN_GROUPS = (
    X_EMBED_DOMAINS,
    INSTAGRAM_EMBED_DOMAINS,
    REDDIT_EMBED_DOMAINS,
)


class LinkFixerView(discord.ui.View):
    def __init__(
        self,
        cog,
        original_message: discord.Message,
        fixed_links: list[str],
        delay: int = 5,
        fallback_timeout: int = 20,
    ):
        super().__init__(timeout=60)
        self.cog = cog
        self.original_message = original_message
        self.fixed_links = fixed_links
        self.delay = delay
        self.fallback_timeout = fallback_timeout
        self.suppression_cancelled = False
        self.bot_message: discord.Message | None = None

        self._suppress_task = asyncio.create_task(self.delayed_suppress())
        self._fallback_task: asyncio.Task | None = None
        if any(self.is_supported_embed_link(link) for link in self.fixed_links):
            self.restart_fallback_timeout()
        else:
            self.remove_button("try_another_embedder")

    def restart_fallback_timeout(self):
        if self._fallback_task and not self._fallback_task.done():
            self._fallback_task.cancel()
        self._fallback_task = asyncio.create_task(
            self.remove_fallback_button_after(self.fallback_timeout)
        )

    def remove_button(self, custom_id: str) -> bool:
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id == custom_id:
                self.remove_item(item)
                return True
        return False

    @staticmethod
    def is_supported_embed_link(link: str) -> bool:
        hostname = urlparse(link).hostname
        return any(hostname in domains for domains in EMBED_DOMAIN_GROUPS)

    @staticmethod
    def use_another_embedder(link: str) -> str:
        parsed = urlparse(link)
        current_domain = parsed.hostname
        for domains in EMBED_DOMAIN_GROUPS:
            if current_domain not in domains:
                continue

            alternatives = [domain for domain in domains if domain != current_domain]
            new_domain = random.choice(alternatives)
            return urlunparse(parsed._replace(netloc=new_domain))

        return link

    async def remove_fallback_button_after(self, timeout: int):
        try:
            await asyncio.sleep(timeout)
            if not self.remove_button("try_another_embedder"):
                return
            if self.bot_message:
                await self.bot_message.edit(view=self)
        except asyncio.CancelledError:
            pass
        except (discord.Forbidden, discord.NotFound):
            pass
        except Exception as e:
            print(f"baj van fallback button eltávolítása közben: {e}")

    async def delayed_suppress(self):
        try:
            await asyncio.sleep(self.delay)

            if self.suppression_cancelled:
                return

            await self.original_message.edit(suppress=True)

            self.remove_button("keep_original")

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
        if self._fallback_task and not self._fallback_task.done():
            self._fallback_task.cancel()

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
        label="Try another embedder",
        style=discord.ButtonStyle.primary,
        custom_id="try_another_embedder"
    )
    async def try_another_embedder(
            self,
            interaction: discord.Interaction,
            button: discord.ui.Button
    ):
        self.restart_fallback_timeout()
        self.fixed_links = [
            self.add_cache_buster(self.use_another_embedder(link))
            if self.is_supported_embed_link(link)
            else link
            for link in self.fixed_links
        ]

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
        for match in self.x_pattern.finditer(message.content):
            domain = random.choice(X_EMBED_DOMAINS)
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
