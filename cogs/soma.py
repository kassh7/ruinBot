import os
import random

import ciso8601
import discord
import pytz
import requests
import time
from datetime import datetime, timezone, timedelta
from PIL import Image
from discord.ext import commands


class Soma(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cd_path = 'usr/somacd.txt'
        # ezt lehet nem ide kéne de at this point leszarom
        if not os.path.exists(self.cd_path):
            with open(self.cd_path, 'w') as file:
                file.write("0")

            print(f"File '{self.cd_path}' created.")
        else:
            print(f"File '{self.cd_path}' already exists.")

    @commands.command(aliases=['soma'])
    async def soma_color(self, ctx):
        try:
            file = open(self.cd_path, 'r')
            cooldown = str(file.readline())
            file.close()
            role = discord.utils.get(ctx.guild.roles, name="soma")
            user = ctx.author
            personal_cd = await self.check_personal_cooldown(user, ctx)
            if role and await self.check_cooldown(cooldown) and personal_cd is True:
                rgb = random.randint(0, 0xFFFFFF)
                random_color = discord.Color(rgb)
                await role.edit(color=random_color)

                embed = discord.Embed(title="kapta", colour=random_color)
                img = Image.new(mode="RGB", size=(50, 50), color=f"{random_color}")
                img.save("usr/soma.png")
                file = discord.File("usr/soma.png")
                embed.set_image(url="attachment://soma.png")
                r = requests.get(f"http://www.thecolorapi.com/id?hex={str(random_color)[1:]}")
                res = r.json()
                embed.add_field(name="az új szín:", value=f"{res['name']['value']}")

                await self.make_cooldown_timestamp(ctx)
                await self.register_win(user, ctx)
                await ctx.send(file=file, embed=embed)
            elif isinstance(personal_cd, timedelta):
                embed = discord.Embed(title="ne spamolj")
                personal_cd = personal_cd + datetime.now()
                personal_cd = personal_cd.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Europe/Budapest'))
                embed.add_field(name="eddig várj még geci",
                                value=f"{personal_cd.strftime("%H:%M:%S")}")
                file = discord.File("res/angry.png")
                embed.set_image(url="attachment://angry.png")
                await ctx.send(file=file, embed=embed, delete_after=30)
                await ctx.message.delete(delay=30)
            else:
                embed = discord.Embed(title="nem kapta")
                embed.add_field(name="te haltál", value="")
                file = discord.File("res/kssz-orban-thumb.png")
                embed.set_image(url="attachment://kssz-orban-thumb.png")
                await self.incur_personal_cooldown(user, ctx)
                await ctx.send(file=file, embed=embed, delete_after=30)
                await ctx.message.delete(delay=30)

        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    @commands.command(aliases=['somalb'])
    async def soma_leaderboard(self, ctx):
        try:
            cursor = self.bot.db.cursor()
            cursor.execute("SELECT user, wins FROM soma WHERE guild = ? AND wins > 0 ORDER BY wins desc",
                           (ctx.guild.id,))
            data = cursor.fetchall()

            if data:
                embed = discord.Embed(title="Somdler Listája")
                field = ""
                for row in data:
                    field = field + f"{self.bot.get_user(row[0]).display_name} - {row[1]} \n"
                embed.add_field(name="Legjobban brusztolók:", value=field)

                await ctx.send(embed=embed)
        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    @commands.command(aliases=['lastwin'])
    async def last_winner(self, ctx):
        try:
            cursor = self.bot.db.cursor()
            cursor.execute("SELECT winner, timestamp FROM somacd ORDER BY id DESC LIMIT 1")
            data = cursor.fetchone()
            if data:
                embed = discord.Embed(title="Legutolsó brusztolás időpontja:")
                timestamp = datetime.strptime(data[1], '%Y-%m-%d %H:%M:%S')
                timestamp = timestamp.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Europe/Budapest'))
                embed.add_field(name=f"{self.bot.get_user(data[0]).display_name} - {timestamp.strftime("%Y-%m-%d %H:%M:%S")}"
                                    , value="")
                await ctx.send(embed=embed)
            else:
                await ctx.send("ajaj")
        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")


    async def check_cooldown(self, cooldown):
        current_time = datetime.now(timezone.utc)
        current_time = current_time.timetuple()
        current_time = time.mktime(current_time)
        delta = float(cooldown) - current_time  # difference between cooldown and current datetime (in seconds)

        if delta <= 0:  # check if the time is passed
            return True
        else:
            return False

    async def make_cooldown_timestamp(self, ctx):
        cooldown_seconds = random.randint(432000, 691200)  # 5-8 days
        future_time = datetime.now(timezone.utc)
        future_time = future_time + timedelta(seconds=cooldown_seconds)
        future_time = future_time.timetuple()
        future_time = time.mktime(future_time)  # Unix timestamp

        with open(self.cd_path, 'w+') as f:
            f.write(str(future_time))
            f.close()
            cursor = self.bot.db.cursor()
            cursor.execute("INSERT INTO somacd (winner, cooldown) VALUES (?, ?)", (ctx.author.id, str(future_time)))
            self.bot.db.commit()

    async def check_personal_cooldown(self, user, ctx):
        cursor = self.bot.db.cursor()
        cursor.execute("SELECT cooldown FROM soma WHERE user = ? AND guild = ?", (user.id, ctx.guild.id))
        data = cursor.fetchone()
        if data:
            if (datetime.now(timezone.utc) - ciso8601.parse_datetime(data[0])) < timedelta(hours=1):
                return timedelta(hours=1) - (datetime.now(timezone.utc) - ciso8601.parse_datetime(data[0]))
            else:
                return True
        else:
            return True

    async def incur_personal_cooldown(self, user, ctx):
        cursor = self.bot.db.cursor()
        cursor.execute('''
                INSERT INTO soma (user, cooldown, guild) 
                VALUES (?, ?, ?) 
                ON CONFLICT(user) 
                DO UPDATE SET cooldown=excluded.cooldown;
                ''', (user.id, datetime.now(timezone.utc), ctx.guild.id))
        self.bot.db.commit()

    async def register_win(self, user, ctx):
        cursor = self.bot.db.cursor()
        cursor.execute("SELECT wins FROM soma WHERE user = ? AND guild = ?", (user.id, ctx.guild.id))
        data = cursor.fetchone()
        if data:
            wins = data[0]
            cursor = self.bot.db.cursor()
            cursor.execute("UPDATE soma SET wins = ? WHERE user = ? AND guild = ?", (wins + 1, user.id, ctx.guild.id))
            self.bot.db.commit()
        else:
            cursor = self.bot.db.cursor()
            cursor.execute('''
                            INSERT INTO soma (user, cooldown, guild, wins) 
                            VALUES (?, ?, ?, ?);
                            ''', (user.id, datetime.now(timezone.utc), ctx.guild.id, 1))
            self.bot.db.commit()


async def setup(bot):
    await bot.add_cog(Soma(bot))
