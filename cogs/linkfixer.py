import discord
from discord.ext import commands
import re
import random

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
        x_domains = ["fxtwitter.com", "vxtwitter.com", "fixupx.com", "girlcockx.com", "hitlerx.com", "cunnyx.com", "stupidpenisx.com"]
        for match in self.x_pattern.finditer(message.content):
            domain = random.choice(x_domains)
            fixed_links.append(f"https://{domain}/{match.group(1)}")

        # --- INSTAGRAM FIX ---
        for match in self.ig_pattern.finditer(message.content):
            fixed_links.append(f"https://kkinstagram.com/{match.group(1)}")

        # --- REDDIT FIX ---
        for match in self.reddit_pattern.finditer(message.content):
            fixed_links.append(f"https://rxddit.com/{match.group(1)}")

        if fixed_links:
            try:
                await message.edit(suppress=True)

                final_message = (
                    f"🗣️ **{message.author.display_name}** küldte:\n" +
                    "\n".join(fixed_links)
                )

                await message.channel.send(final_message)
            except discord.Forbidden:
                print(f"baj van: Nincs jogom elrejteni az embedet itt: {message.channel.name}")
            except Exception as e:
                print(f"baj van: {e}")

async def setup(bot):
    await bot.add_cog(LinkFixer(bot))