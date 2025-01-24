import datetime
import json
import os
import random

import discord
import requests
from requests.exceptions import RequestException
from bs4 import BeautifulSoup
from discord.ext import commands, tasks
from requests import TooManyRedirects

utc = datetime.timezone.utc

# If no tzinfo is given then UTC is assumed.
time = datetime.time(hour=int(os.getenv("MORNING_HOUR")), minute=int(os.getenv("MORNING_MINUTE")), tzinfo=utc)

async def scrape():
    url = 'http://www.idokep.hu'

    try:
        response = requests.get(url)
        response.raise_for_status()
    except RequestException as e:
        print(f"Error fetching data from {url}: {e}")
        return False
    if response.status_code != 200:
        return False
    else:
        soup = BeautifulSoup(response.content, 'html.parser')

        what_to_wear = [element.get_text(strip=True) for element in soup.select('.what-to-wear')]
        current_temperature = [element.get_text(strip=True) for element in soup.select('.current-temperature')]
        current_weather = [element.get_text(strip=True) for element in soup.select('.current-weather')]
        daily_max_temperature = [element.get_text(strip=True) for element in soup.select('.dailyForecastCol:nth'
                                                                                         '-child(2) .max a,'
                                                                                         '.dailyForecastCol:nth'
                                                                                         '-child(2) .min-max-closer '
                                                                                         'a:nth-child(1),'
                                                                                         '.dailyForecastCol:nth'
                                                                                         '-child(2) .min-max-close '
                                                                                         'a:nth-child(1)')]
        alert = [element.get_text(strip=True) for element in soup.select('#topalertbar > a:nth-child(1)')]

        return {
            'what_to_wear': "".join(what_to_wear),
            'current_temperature': "".join(current_temperature),
            'current_weather': "".join(current_weather),
            'daily_max_temperature': "".join(daily_max_temperature),
            'alert': "; ".join(alert)
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


async def make_morning_message():
    morning_json = json.load(open('res/morning.json', "r", encoding='utf-8'))
    random.seed(str(datetime.date.today()))
    embed = discord.Embed(title=f"{random.choice(morning_json['greeting'])} {random.choice(morning_json['address'])}! "
                                f":sun_with_face: ")
    try:
        r = requests.get("https://api.nevnapok.eu/ma", timeout=10)
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
        names_string = f"Befosott, behányt, sírgödörbe lökték a névnapok apit: {e}"

    weather = await scrape()

    embed.add_field(name="Mai névnapok :partying_face:", value=names_string, inline=False)
    if weather:
        if weather['current_temperature']:
            embed.add_field(name="Jelenlegi hőmérséklet :thermometer:", value=weather['current_temperature'], inline=True)
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
                                                                   "Befosott, behányt, sírgödörbe lökték a névnapok apit"]))
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
            embed = await make_morning_message()
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    @tasks.loop(time=time)
    async def morning_message_task(self):
        print('Sending morning message')
        try:
            system_channels = []
            for guild in self.bot.guilds:
                # Get the system channel for the guild
                system_channel = guild.system_channel
                if system_channel:  # Check if the guild has a system channel
                    try:
                        system_channels.append(system_channel)
                    except discord.Forbidden:
                        print(f"Bot doesn't have permission to send messages to the system channel of {guild.name}.")
                else:
                    print(f"No system channel found for {guild.name}.")
            for channel in system_channels:
                embed = await make_morning_message()
                await channel.send(embed=embed)
        except Exception as e:
            print(f"baj van: {e}")
            await channel.send(f"baj van: {e}")


async def setup(bot):
    await bot.add_cog(Morning(bot))
