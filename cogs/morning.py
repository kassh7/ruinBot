import datetime
import json
import os
import random

import discord
import requests
from bs4 import BeautifulSoup
from discord.ext import commands, tasks

utc = datetime.timezone.utc

# If no tzinfo is given then UTC is assumed.
time = datetime.time(hour=6, minute=0, tzinfo=utc)
MORNING = os.getenv("MORNING")


async def scrape():
    url = 'http://www.idokep.hu'  # Replace with your target URL
    response = requests.get(url)

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
            'alert': "".join(alert)
        }


async def send_morning_message(channel):
    morning_json = json.load(open('res/morning.json', "r", encoding='utf-8'))
    random.seed(str(datetime.date.today()))
    embed = discord.Embed(title=f"{random.choice(morning_json['greeting'])} {random.choice(morning_json['address'])}! "
                                f":sun_with_face: ")

    r = requests.get("https://api.nevnapok.eu/ma")
    res = r.json()
    all_names = []
    for names in res.values():
        all_names.extend(names)
    names_string = ", ".join(all_names)

    weather = await scrape()

    embed.add_field(name="Mai névnapok :partying_face:", value=names_string, inline=False)
    if weather['current_temperature']:
        embed.add_field(name="Jelenlegi hőmérséklet :thermometer:", value=weather['current_temperature'], inline=True)
    if weather['current_weather']:
        embed.add_field(name='Időjárás :partly_sunny: ', value=weather['current_weather'], inline=True)
    embed.add_field(name=chr(173), value=chr(173))
    if weather['daily_max_temperature']:
        embed.add_field(name="Max :thermometer:", value=f"{weather['daily_max_temperature']}˚C", inline=True)
    if weather['what_to_wear']:
        embed.add_field(name="Mit vegyél fel? :womans_clothes:", value=weather['what_to_wear'], inline=True)
    if weather['alert']:
        embed.add_field(name=chr(173), value=chr(173))
        embed.add_field(name="Figyelmeztetés :exclamation: ", value=weather['alert'], inline=False)
    await channel.send(embed=embed)


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
            await send_morning_message(ctx)
        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    @tasks.loop(time=time)
    async def morning_message_task(self):
        morning_channel = self.bot.get_channel(int(MORNING))
        try:
            await send_morning_message(morning_channel)
        except Exception as e:
            print(f"baj van: {e}")
            await morning_channel.send(f"baj van: {e}")


async def setup(bot):
    await bot.add_cog(Morning(bot))
