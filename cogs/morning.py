import datetime
import json
import os
import random

import brotli
import discord
import requests
from requests.exceptions import RequestException
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from discord.ext import commands, tasks
from requests import TooManyRedirects

utc = datetime.timezone.utc

# If no tzinfo is given then UTC is assumed.
time = datetime.time(hour=int(os.getenv("MORNING_HOUR")), minute=int(os.getenv("MORNING_MINUTE")), tzinfo=utc)


def get_retry_session(
        total_retries=5,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=None
):
    """
    Returns a requests.Session() that retries requests on temporary errors.
    """
    session = requests.Session()
    if allowed_methods is None:
        allowed_methods = ["GET", "POST", "HEAD", "OPTIONS"]
    retries = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=allowed_methods,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


async def scrape():
    url = 'http://www.idokep.hu'
    session = get_retry_session()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Accept-Encoding': 'br, gzip, deflate',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }

    try:
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except RequestException as e:
        print(f"Error fetching data from {url}: {e}")
        return False

    content_encoding = response.headers.get("Content-Encoding", "").lower()

    try:
        if "br" in content_encoding:
            decoded_html = brotli.decompress(response.content).decode("utf-8")
        elif "gzip" in content_encoding:
            decoded_html = zlib.decompress(response.content, 16 + zlib.MAX_WBITS).decode("utf-8")
        elif "deflate" in content_encoding:
            decoded_html = zlib.decompress(response.content).decode("utf-8")
        else:
            decoded_html = response.text
    except Exception as e:
        print(f"Decompression failed: {e}")
        decoded_html = response.text

    soup = BeautifulSoup(decoded_html, "html.parser")

    what_to_wear = soup.select_one('.what-to-wear')
    current_temperature = soup.select_one('.current-temperature')
    current_weather = soup.select_one('.current-weather')
    daily_max = soup.select_one('.dailyForecastCol .max a')
    alert = soup.select_one('#topalertbar a')

    return {
        'what_to_wear': what_to_wear.get_text(strip=True) if what_to_wear else '',
        'current_temperature': current_temperature.get_text(strip=True) if current_temperature else '',
        'current_weather': current_weather.get_text(strip=True) if current_weather else '',
        'daily_max_temperature': daily_max.get_text(strip=True) if daily_max else '',
        'alert': alert.get_text(strip=True) if alert else ''
    }


async def generate_day():
    current_date = datetime.datetime.now()
    day_eng = current_date.strftime('%A')
    day_translation = {
        "Monday": "Hétfő",
        "Tuesday": "Kedd",
        "Wednesday": "Szerda",
        "Thursday": "Csütörtök",
        "Friday": "Péntek",
        "Saturday": "Szombat",
        "Sunday": "Vasárnap"
    }
    day = day_translation.get(day_eng)

    adjective_json = json.load(open('res/adjective.json', "r", encoding='utf-8'))
    adjective = random.choice(adjective_json[day[0].lower()])
    if datetime.datetime.now().date() == datetime.datetime.strptime(os.getenv("SPECIAL_DATE", ""), "%Y-%m-%d").date():
        adjective = os.getenv("SPECIAL_ADJECTIVE")
    day_name = f"{adjective.capitalize()} {day}"
    return day_name


async def generate_month():
    current_date = datetime.datetime.now()
    month_eng = current_date.strftime('%B')
    month_translation = {
        "January": "Január",
        "February": "Február",
        "March": "Március",
        "April": "Április",
        "May": "Május",
        "June": "Június",
        "July": "Július",
        "August": "Augusztus",
        "September": "Szeptember",
        "October": "Október",
        "November": "November",
        "December": "December"
    }
    month = month_translation.get(month_eng)

    adjective_json = json.load(open('res/adjective.json', "r", encoding='utf-8'))
    adjective = random.choice(adjective_json[month[0].lower()])
    if datetime.datetime.now().date() == datetime.datetime.strptime(os.getenv("SPECIAL_DATE", ""), "%Y-%m-%d").date():
        adjective = os.getenv("SPECIAL_ADJECTIVE")
    month_name = f"{adjective.capitalize()} {month}"
    return month_name


async def make_morning_message(command = False):
    morning_json = json.load(open('res/morning.json', "r", encoding='utf-8'))
    random.seed(datetime.date.today().strftime("%Y%m"))
    month = await generate_month()
    random.seed(str(datetime.date.today()))
    embed = discord.Embed(title=f"{random.choice(morning_json['greeting'])} {random.choice(morning_json['address'])}! "
                                f":sun_with_face: ")

    session = get_retry_session()

    try:
        r = session.get("https://api.nevnapok.eu/ma", timeout=10)
        r.raise_for_status()
        res = r.json()
        all_names = []
        for names in res.values():
            all_names.extend(names)
        if all_names:
            names_string = ", ".join(all_names)
        else:
            names_string = "Befosott a névnapok api."
    except TooManyRedirects:
        names_string = "Sírgödörbe lökték a névnapok apit, ráhányják a földet is"
    except requests.exceptions.RequestException as e:
        names_string = f"Befosott, behányt, sírgödörbe lökték a névnapok apit"

    weather = await scrape()

    embed.add_field(name="Mai névnapok :partying_face:", value=names_string, inline=False)
    if weather:
        if weather['current_temperature']:
            embed.add_field(name="Jelenlegi hőmérséklet :thermometer:", value=weather['current_temperature'],
                            inline=True)
        if weather['current_weather']:
            embed.add_field(name='Időjárás :partly_sunny: ', value=weather['current_weather'], inline=True)
        embed.add_field(name=chr(173), value=chr(173))
        if weather['daily_max_temperature']:
            embed.add_field(name="Max :thermometer:", value=f"{weather['daily_max_temperature']}˚C", inline=True)
        if weather['what_to_wear']:
            embed.add_field(name="Mit vegyél fel? :womans_clothes:", value=weather['what_to_wear'], inline=True)
        embed.add_field(name=chr(173), value=chr(173))
        if weather['alert']:
            embed.add_field(name="Figyelmeztetés :exclamation: ", value=weather['alert'], inline=False)
    else:
        embed.add_field(name="Időkép status", value=random.choice(["Befosott az időkép.",
                                                                   "Sírgödörbe lökték az időképet, ráhányják a földet is",
                                                                   "Befosott, behányt, sírgödörbe lökték az időképet"]))
    if datetime.date.today().day == 1:
        embed.add_field(name=f"Mától {month}t írunk.", value="", inline=False)
    elif command:
        embed.add_field(name=f"A jelenlegi hónap {month}.", value="", inline=False)
    embed.add_field(name=f"Ma {await generate_day()} van.", value="", inline=False)
    return embed


class Morning(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.morning_message_task.start()

    def cog_unload(self):
        self.morning_message_task.cancel()

    @commands.hybrid_command(name="morning", with_app_command=True,
                             description="jóreggelt pupernyákoló")
    async def morning_message(self, ctx):
        try:
            embed = await make_morning_message(command=True)
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    @tasks.loop(time=time)
    async def morning_message_task(self):
        try:
            system_channels = []
            for guild in self.bot.guilds:
                # Get the system channel for the guild
                system_channel = guild.system_channel
                if system_channel:
                    # Check if the bot has permission to send messages in the system channel
                    permissions = system_channel.permissions_for(guild.me)
                    if permissions.send_messages:
                        try:
                            system_channels.append(system_channel)
                        except discord.Forbidden:
                            print(f"Bot is forbidden from sending messages in {guild.name}'s system channel.")
                        except discord.HTTPException as e:
                            print(f"HTTPException occurred in {guild.name}: {e}")
                    else:
                        print(f"Bot lacks permissions to send messages in {guild.name}'s system channel.")
                else:
                    print(f"No system channel found for {guild.name}.")
            embed = await make_morning_message()
            for channel in system_channels:
                try:
                    await channel.send(embed=embed)
                except Exception as e:
                    print(f"baj van: {e}")
                    await channel.send(f"baj van: {e}")
        except Exception as e:
            print(f"baj van: {e}")


async def setup(bot):
    await bot.add_cog(Morning(bot))
