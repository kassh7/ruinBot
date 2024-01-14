import asyncio
import logging

import discord
import os
import sqlite3

from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
cogs_dir = "cogs"
#logging.basicConfig(level=logging.DEBUG)

intents = discord.Intents.all()
intents.members = True
bot = commands.Bot(command_prefix="r!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    bot.db = sqlite3.connect("usr/db.sqlite")
    cursor = bot.db.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS soma(user INTEGER UNIQUE, cooldown timestamp, guild INTEGER, wins INTEGER)")
    bot.db.commit()

    await bot.change_presence(activity=discord.Game('anyáddal'))
    print("na re")

    kodolo_chan = bot.get_channel(544959530723835944)
    #await kodolo_chan.send("na re")


async def load_cogs():
    # load cogs
    for filename in os.listdir(cogs_dir):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'{filename} loaded')
            except Exception as e:
                print(f"baj van: {e}")


async def main():
    await load_cogs()
    await bot.start(TOKEN)

asyncio.run(main(), debug=True)
