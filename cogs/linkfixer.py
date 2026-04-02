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

        original_content = message.content
        new_content = original_content
        changed = False

        # --- TWITTER / X FIX ---
        if self.x_pattern.search(new_content):
            x_domains = ["fxtwitter.com", "vxtwitter.com", "fixupx.com", "girlcockx.com", "hitlerx.com", "cunnyx.com"]

            def replace_x(match):
                domain = random.choice(x_domains)
                return f"https://{domain}/{match.group(1)}"

            new_content = self.x_pattern.sub(replace_x, new_content)
            changed = True

        # --- INSTAGRAM FIX ---
        if self.ig_pattern.search(new_content):
            new_content = self.ig_pattern.sub(r'https://kkinstagram.com/\1', new_content)
            changed = True

        # --- REDDIT FIX ---
        if self.reddit_pattern.search(new_content):
            new_content = self.reddit_pattern.sub(r'https://rxddit.com/\1', new_content)
            changed = True

        if changed:
            try:
                await message.delete()

                # We put their name in bold so people know who sent it!
                final_message = f"🗣️ **{message.author.display_name}** küldte:\n{new_content}"

                # If they replied to someone, we should try to keep the reply context!
                if message.reference:
                    await message.channel.send(final_message, reference=message.reference)
                else:
                    await message.channel.send(final_message)

            except discord.Forbidden:
                print(f"baj van: Nincs jogom törölni az üzenetet itt: {message.channel.name}")
            except Exception as e:
                print(f"baj van: {e}")

async def setup(bot):
    await bot.add_cog(LinkFixer(bot))
