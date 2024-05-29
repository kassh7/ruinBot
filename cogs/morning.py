import datetime
import os

import discord
import requests
from discord.ext import commands, tasks

utc = datetime.timezone.utc

# If no tzinfo is given then UTC is assumed.
time = datetime.time(hour=6, minute=0, tzinfo=utc)
MORNING = os.getenv("MORNING")


class morning(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.morning_message.start()

    def cog_unload(self):
        self.morning_message.cancel()

    @tasks.loop(time=time)
    async def morning_message(self):
        morning_channel = self.bot.get_channel(int(MORNING))
        embed = discord.Embed(title="Jóreggelt pupákok!")

        r = requests.get("https://api.nevnapok.eu/ma")
        res = r.json()
        all_names = []
        for names in res.values():
            all_names.extend(names)
        names_string = ", ".join(all_names)

        embed.add_field(name="Mai névnapok", value=names_string)
        await morning_channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(morning(bot))
