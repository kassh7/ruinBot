import random
import discord
import requests
from PIL import Image
from discord.ext import commands


class soma(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['soma'])
    async def soma_color(self, ctx):
        # todo: random cooldown, ha cdn van akkor halt és 1 óra personal cd
        try:
            role = discord.utils.get(ctx.guild.roles, name="soma")
            if role:
                rgb = random.randint(0, 0xFFFFFF)
                random_color = discord.Color(rgb)
                await role.edit(color=random_color)
                embed = discord.Embed(title="kapta", colour=random_color)
                img = Image.new(mode="RGB", size=(50, 50), color=f"{random_color}")
                img.save("res/soma.png")
                file = discord.File("res/soma.png")
                embed.set_image(url="attachment://soma.png")
                r = requests.get(f"http://www.thecolorapi.com/id?hex={str(random_color)[1:]}")
                res = r.json()
                embed.add_field(name="az új szín:", value=f"{res['name']['value']}")
                await ctx.send(file=file, embed=embed)
        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")
async def setup(bot):
    await bot.add_cog(soma(bot))