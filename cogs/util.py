import os
from typing import Optional, Literal

import discord
import requests
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

    async def get_token(self):
        headers = {
            'accept': 'application/json, text/plain, */*',
            'content-type': 'application/json'
        }
        data = {
            'username': self.username,
            'password': self.password
        }
        response = requests.post(self.auth_url, headers=headers, json=data)
        if response.status_code == 200:
            self.token = response.json().get('jwt')
            if not self.token:
                raise ValueError("Token not found in the response. How typical...")
        else:
            raise Exception("Failed to get token. Because why would anything work?")

    async def restart_zenebot(self):
        if self.token is None:
            raise Exception("No token found. Get the token first, genius.")

        headers = {
            'accept': 'application/json, text/plain, */*',
            'content-type': 'application/json',
            'authorization': f'Bearer {self.token}'
        }
        response = requests.post(self.restart_url, headers=headers, json={})
        if response.status_code == 204:
            return "Zenebot successfully restarted. Miracles do happen."
        else:
            raise Exception(
                f"Failed to restart Zenebot. Response: {response.status_code}, {response.text}. What a shocker.")

    # Usage example
    @commands.hybrid_command(name="kozel", with_app_command=True,
                             description="kozelbot újraindítós")
    async def restart_kozel(self,ctx):
        try:
            await self.get_token()
            await ctx.reply(await self.restart_zenebot())
        except Exception as e:
            print(f"An error occurred: {e}. But of course it did.")
            ctx.reply(f"An error occurred: {e}. But of course it did.")

async def setup(bot):
    await bot.add_cog(Util(bot))
