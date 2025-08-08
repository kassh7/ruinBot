import os
import random

from discord.utils import get
from discord.ext import commands, tasks


class Cz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="cz", with_app_command=True,
                             description="czegenyszki")
    async def command_cz(self, ctx):
        try:
            if ctx.guild is None or int(ctx.guild.id) != int(os.getenv("CZ_SERV")):
                return

            author = ctx.author.display_name
            #if self.bot.state.is_expired("cz"): // todo
            newnick = self.get_breveg
            #self.bot.state.add_timeout("cz", expiry_td=datetime.timedelta(minutes=1))
            member = get(ctx.channel.members, id=int(os.getenv("CZ")))
            await member.edit(nick=newnick)
            await ctx.send(f"{author} szerint: {member.mention}")
            if ctx.interaction is None and ctx.message:
                await ctx.message.delete()

            # Append the generated nickname to the "nevek.txt" file
            with open("usr/nevek.txt", "a", encoding="utf-8") as f:
                f.write(f"{newnick}\n")
            #else:
            #    await ctx.response.send_message("pill...")
        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    @property
    def get_breveg(self):
        consonants = [char for char in "bcdfghjklmnpqrstvwxz"] + ["gy", "cz", "dzs", "ty", "br", "cs"]
        prebuilts = [
            "hét", "gét", "rét", "új", "már", "gép", "tér", "vér", "zágráb", "zárt", "kétabony", "hosszú", "bánat",
            "dér", "szar", "egy", "két", "cék", "nagy"
        ]
        enders = [
            "végi", "helyi", "ési", "réti", "gényi", "esi", "melletti", "közi", "kerti", "faszú", "téri", "falvi",
            "fejű", "házi", "lányi", "orrú"
        ]

        out = ""
        if random.choice([True, False]):
            pre = random.choice(prebuilts)
            out += pre
            if pre == "dér" and random.randrange(0, 100) > 40:
                out += "heni"
            else:
                out += random.choice(enders)
        else:
            start = random.choice(consonants) + "é"
            end = random.choice(enders)
            mid = random.choice(consonants) if (start[-1:] not in consonants and end[:-1] not in consonants) \
                                               or random.choice([True, False]) else ""
            out = f"{start}{mid}{end}"

        return out.capitalize()


async def setup(bot):
    await bot.add_cog(Cz(bot))
