import datetime
import os

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
        what_to_wear = ""
        current_temperature = ""
        soup = BeautifulSoup(response.content, 'html.parser')
        what_to_wear_elements = soup.select('.what-to-wear')
        what_to_wear_results = [element.get_text(strip=True) for element in what_to_wear_elements]
        current_temperature_elements = soup.select('.current-temperature')
        current_temperature_results = [element.get_text(strip=True) for element in current_temperature_elements]

        if what_to_wear_results:
            what_to_wear = '\n'.join(what_to_wear_results)
        if current_temperature_results:
            current_temperature = '\n'.join(current_temperature_results)

        return {
            'what_to_wear': what_to_wear,
            'current_temperature': current_temperature
        }



class morning(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.morning_message_task.start()

    def cog_unload(self):
        self.morning_message_task.cancel()

    @commands.hybrid_command(name="morning", with_app_command=True,
                             description="jóreggelt pupernyákoló")
    async def morning_message(self, ctx):
        morning_channel = self.bot.get_channel(int(MORNING))
        try:
            embed = discord.Embed(title="Jóreggelt pupákok! :sun_with_face: ")

            r = requests.get("https://api.nevnapok.eu/ma")
            res = r.json()
            all_names = []
            for names in res.values():
                all_names.extend(names)
            names_string = ", ".join(all_names)

            weather = await scrape()

            embed.add_field(name="Mai névnapok :partying_face: ", value=names_string, inline=False)
            if weather['current_temperature']:
                embed.add_field(name="Időjárás :partly_sunny: ", value=weather['current_temperature'])
            if weather['what_to_wear']:
                embed.add_field(name="Mit vegyél fel? :womans_clothes: ", value=weather['what_to_wear'])
            await morning_channel.send(embed=embed)
        except Exception as e:
            print(f"baj van: {e}")
            await morning_channel.send(f"baj van: {e}")

    @tasks.loop(time=time)
    async def morning_message_task(self):
        morning_channel = self.bot.get_channel(int(MORNING))
        try:
            embed = discord.Embed(title="Jóreggelt pupákok! :sun_with_face: ")

            r = requests.get("https://api.nevnapok.eu/ma")
            res = r.json()
            all_names = []
            for names in res.values():
                all_names.extend(names)
            names_string = ", ".join(all_names)

            weather = await scrape()

            embed.add_field(name="Mai névnapok :partying_face: ", value=names_string, inline=False)
            if weather['current_temperature']:
                embed.add_field(name="Jelenlegi hőmérséklet :thermometer:  ", value=weather['current_temperature'])
            if weather['what_to_wear']:
                embed.add_field(name="Mit vegyél fel? :womans_clothes: ", value=weather['what_to_wear'])
            await morning_channel.send(embed=embed)
        except Exception as e:
            print(f"baj van: {e}")
            await morning_channel.send(f"baj van: {e}")


async def setup(bot):
    await bot.add_cog(morning(bot))
