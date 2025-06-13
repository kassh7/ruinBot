import json
import random
import os
import discord
import random

from discord.ext import commands


class Kifogas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        with open("res/kifogasok.json", "r", encoding='utf-8') as f:
            self.kifogas_json = json.load(f)

    @commands.hybrid_command(name="kifogas", with_app_command=True,
                             description="kifogás generátor")
    async def kifogas(self, ctx):
        kifogas = await self.generate_kifogas(ctx)
        await ctx.reply(kifogas)

    async def generate_kifogas(self, ctx):
        kifogas_affix = random.choice(self.kifogas_json['prefixes'])
        kifogas_suffix = random.choice(self.kifogas_json['suffixes'])
        if "%s" in kifogas_suffix:
            kifogas_suffix = kifogas_suffix.replace("%s", random.choice(ctx.channel.members).mention)
        return f"{kifogas_affix} {kifogas_suffix}"

async def setup(bot):
    await bot.add_cog(Kifogas(bot))
