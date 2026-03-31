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

    @commands.hybrid_command(name="gork", with_app_command=True,
                             description="Gork megmondja az igazságot")
    async def grok(self, ctx):
        await self.send_grok(ctx)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if "gork ez igaz" in message.content.lower():
            await self.send_grok(message)


async def setup(bot):
    await bot.add_cog(Grok(bot))
