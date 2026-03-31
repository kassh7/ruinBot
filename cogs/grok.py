

import random

import discord
from discord.ext import commands


class Grok(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_grok(self, target):
        filename = random.choice(["ye.jpg", "nah.jpg"])
        file = discord.File(f"res/{filename}")
        await target.reply(file=file)

    @commands.hybrid_command(
        name="gork",
        with_app_command=True,
        description="Gork megmondja az igazságot"
    )
    async def grok(self, ctx):
        await self.send_grok(ctx)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        content = message.content.lower()

        triggers = ["gork", "grok", "groj"]
        truth_phrases = ["ez igaz", "is this true"]

        has_name = any(word in content for word in triggers)
        is_mentioned = self.bot.user in message.mentions
        has_truth = any(phrase in content for phrase in truth_phrases)

        if (has_name or is_mentioned) and has_truth:
            await self.send_grok(message)

        # keep commands working
        await self.bot.process_commands(message)


async def setup(bot):
    await bot.add_cog(Grok(bot))