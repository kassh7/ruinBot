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
        
        @bot.tree.context_menu(name="jerma985")
		async def nyomod(interaction: discord.Interaction, message: discord.Message):
			await message.reply(random.choice(["-","+"]) + str(random.randrange(1,3)))
			await interaction.response.send_message(content="hehe", ephemeral=True, delete_after=1)

    @commands.hybrid_command(name="kifogas", with_app_command=True,
                             description="kifogás generátor")
    async def kifogas(self, ctx):
        kifogas = await self.generate_kifogas(ctx)
        await ctx.reply(kifogas)random.choice(["-","+"])+str(random.randrange(1,3))

    async def generate_kifogas(self, ctx):
        kifogas_affix = random.choice(self.kifogas_json['prefixes'])
        kifogas_suffix = random.choice(self.kifogas_json['suffixes'])
        if "%s" in kifogas_suffix:
            kifogas_suffix = kifogas_suffix.replace("%s", random.choice(ctx.channel.members).mention)
        return f"{kifogas_affix} {kifogas_suffix}"

async def setup(bot):
    await bot.add_cog(Kifogas(bot))
