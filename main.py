import asyncio
import discord
import os

from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
cogs_dir = "cogs"

intents = discord.Intents.all()
intents.members = True
bot = commands.Bot(command_prefix="r!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    print("na re")
    await bot.change_presence(activity=discord.Game('anyáddal'))
    # for guild in bot.guilds:
    #    await guild.system_channel.send("na re")


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

asyncio.run(main())
