import os
from typing import Optional, Literal

import discord
import random
import subprocess
from discord.ext import commands
from discord.ext.commands import Context, Greedy

class Util(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auth_url = os.getenv("KOZEL_AUTH_URL")
        self.restart_url = os.getenv("KOZEL_RESTART_URL")
        self.username = os.getenv("KOZEL_USER")
        self.password = os.getenv("KOZEL_PASS")
        self.token = None

        @bot.tree.context_menu(name="jerma985")
        async def nyomod(interaction: discord.Interaction, message: discord.Message):
            await message.reply(random.choice(["-","+"]) + str(random.randrange(1,3)))
            await interaction.response.send_message(content="hehe", ephemeral=True, delete_after=1)

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
        try:
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

        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    @commands.command(name="start_musicbot", hidden=True)
    @commands.is_owner()
    async def start_musicbot(self, ctx):
        try:
            result = subprocess.run(
                ["docker", "compose", "up", "-d"],
                cwd=os.path.expanduser("~/MusicBot"),
                capture_output=True, text=True, check=True
            )
            await ctx.send("🎵 RuinBástya container started.")
        except subprocess.CalledProcessError as e:
            await ctx.send(f"❌ Failed to start container:\n```{e.stderr}```")

    @commands.command(name="stop_musicbot", hidden=True)
    @commands.is_owner()
    async def stop_musicbot(self, ctx):
        try:
            result = subprocess.run(
                ["docker", "compose", "down"],
                cwd=os.path.expanduser("~/MusicBot"),
                capture_output=True, text=True, check=True
            )
            await ctx.send("🛑 RuinBástya container stopped.")
        except subprocess.CalledProcessError as e:
            await ctx.send(f"❌ Failed to stop container:\n```{e.stderr}```")


async def setup(bot):
    await bot.add_cog(Util(bot))
