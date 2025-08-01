import asyncio


import discord
import os
import sqlite3

from discord.ext import commands
from dotenv import load_dotenv
import logging

# Main logging config
logging.basicConfig(
    level=logging.INFO,  # Set root level to INFO to avoid spam
    filename='ruinbot.log',
    filemode='a',
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
)

# Console output (optional)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('[%(levelname)s] %(message)s')
console.setFormatter(formatter)
logging.getLogger().addHandler(console)

# Silence discord.py's debug spam
logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('discord.gateway').setLevel(logging.ERROR)
logging.getLogger('websockets').setLevel(logging.ERROR)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
NARE = os.getenv("CHANNEL")
cogs_dir = "cogs"

intents = discord.Intents.all()
intents.members = True
bot = commands.Bot(command_prefix="r!", intents=intents, help_command=None,
                   allowed_mentions=discord.AllowedMentions(roles=False, users=False, everyone=False))


@bot.event
async def on_ready():
    bot.db = sqlite3.connect("usr/db.sqlite")
    cursor = bot.db.cursor()
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS soma(user INTEGER UNIQUE, cooldown timestamp, guild INTEGER, wins INTEGER DEFAULT '
        '0 NOT NULL)')
    bot.db.commit()
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS somacd(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DEFAULT CURRENT_TIMESTAMP, '
        'winner INTEGER, cooldown timestamp)')
    bot.db.commit()
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS soma_tries'
        '(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DEFAULT CURRENT_TIMESTAMP, '
        'on_personal INTEGER, user INTEGER)')
    bot.db.commit()
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS soma_wins'
        '(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DEFAULT CURRENT_TIMESTAMP, user_id INTEGER)')
    bot.db.commit()

    await bot.change_presence(activity=discord.Game('anyáddal'))
    await bot.tree.sync(guild=discord.Object(id=232227916036046849))
    print("na re")
    kodolo_chan = bot.get_channel(int(NARE))
    await kodolo_chan.send("na re")


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
