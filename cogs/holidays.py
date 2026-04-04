import discord
from discord.ext import commands
from datetime import datetime
from utils.holiday_cache import get_holidays

DAY_NAMES = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek", "Szombat", "Vasárnap"]


class Holidays(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        name="unnepnapok",
        with_app_command=True,
        description="Kilistázza az év hátralévő munkaszüneti napjait 🇭🇺"
    )
    async def unnepnapok(self, ctx):
        today = datetime.now().date()

        try:
            holidays = await get_holidays(today.year)
        except Exception as e:
            await ctx.send(f"baj van: {e}")
            return

        if not holidays:
            await ctx.send("baj van: nem sikerült lekérni az ünnepnapokat!")
            return

        # Filter: only future holidays on workdays (Mon-Fri)
        free_days = []
        for h in holidays:
            date = datetime.strptime(h['date'], "%Y-%m-%d").date()
            if date >= today and date.weekday() < 5:
                free_days.append({
                    "date": date,
                    "localName": h['localName'],
                    "day": DAY_NAMES[date.weekday()],
                    "days_until": (date - today).days
                })

        if not free_days:
            await ctx.send("😢 Nincs több munkaszüneti nap idén... kibírjuk valahogy.")
            return

        embed = discord.Embed(
            title=f"🇭🇺 Munkaszüneti napok {today.year}",
            description="Hátralévő hétköznapra eső ünnepek\n(mert a hétvégire eső ügyis lófasz 😤)",
            color=0xC8102E
        )

        for day in free_days:
            if day['days_until'] == 0:
                countdown = "🎉 **MA VAN!**"
            elif day['days_until'] == 1:
                countdown = "🎊 Holnap!"
            else:
                countdown = f"{day['days_until']} nap múlva"

            embed.add_field(
                name=f"📅 {day['date'].strftime('%Y.%m.%d')} ({day['day']})",
                value=f"{day['localName']} — {countdown}",
                inline=False
            )

        embed.set_footer(text=f"Összesen {len(free_days)} szabad nap van hátra idén 🎉")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Holidays(bot))
