from typing import Optional, Literal

import discord
from discord.ext import commands
from discord.ext.commands import Context, Greedy


class ping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def ping(self, ctx):
        await ctx.reply(f"Pong {round(self.bot.latency * 1000)}ms")

    @commands.command(name="sync", hidden=True)
    @commands.guild_only()
    @commands.is_owner()
    async def sync(self, ctx: Context, guilds: Greedy[discord.Object],
                   spec: Optional[Literal["~", "*", "^"]] = None) -> None:
        """
            do bist stollen
            synchronizes slash commands with server
        """
        await ctx.message.delete()
        if not guilds:
            if spec == "~":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "^":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                synced = []
            else:
                synced = await ctx.bot.tree.sync()

            await ctx.send(
                f"{len(synced)} trükköt tud a báttya{'!' if spec is None else '!?'}"
            )
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.send(f"tanit a báttya {ret}/{len(guilds)}.")


async def setup(bot):
    await bot.add_cog(ping(bot))
