import json
import random
from random import randint

import discord
import os

from discord import app_commands
from discord.ext import commands
import markovify


class Markov(commands.Cog):
    def __init__(self, bot):
        self.text_model = None
        self.bot = bot

        if not os.path.exists("usr/markov/"):
            os.mkdir("usr/markov/")
        try:
            with open("usr/markov_config.json", "r", encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = {
                "state_size": 1,
                "tries": 100
            }
            with open("usr/markov_config.json", "w") as file:
                json.dump(self.config, file)

    @commands.Cog.listener()
    async def on_message(self, message):
        if f"<@{self.bot.user.id}>" in message.content:
            await self.markov(message)

        if message.type == discord.MessageType.reply:
            reference = await message.channel.fetch_message(
                message.reference.message_id)

            if reference.author.id == self.bot.user.id:
                await self.markov(message)
        start_filters = ("$", "r!", "<@1197841378961543198>", "<@1194709611077435466>")
        if message.author.bot or not message.content or message.content.startswith(start_filters):
            return
        if message.content.startswith("https://"):
            embeds = [".gif", ".mp4", ".png", ".gif", ".gifv", ".webm", ".jpg", ".jpeg", "tenor.com"]
            if any(ext in message.content for ext in embeds):
                with open(f"usr/markov/urls.txt", "a", encoding='utf-8') as f:
                    f.write(message.content + "\n")
            return

        with open(f"usr/markov/{message.channel}.txt", "a", encoding='utf-8') as f:
            f.write(message.content + "\n")

    @commands.command(aliases=['mark'])
    async def markov(self, ctx):
        text = ""
        for filename in os.listdir("usr/markov/"):
            with open(os.path.join("usr/markov/", filename), 'r', encoding='utf-8') as f:
                if filename == "urls.txt":
                    urls = f.readlines()
                else:
                    text = text + f.read()

        if not self.text_model:
            self.text_model = markovify.NewlineText(text, state_size=self.config["state_size"])

        chance = randint(1, 100)
        if chance > 10:
            sentence = self.text_model.make_sentence(tries=self.config["tries"])
        else:
            sentence = random.choice(urls)

        await ctx.reply(sentence if sentence else "MIT MOND?")

    @commands.hybrid_command(name="config", with_app_command=True,
                             description="Change the markov config (state_size, tries)")
    @app_commands.guilds(discord.Object(id=232227916036046849))
    @app_commands.describe(config_name='state_size or tries')
    async def markov_config(self, ctx, config_name: str, value: int):
        if config_name in ("state_size", "tries"):
            await ctx.send(f"{config_name} changed to {value} from {self.config[config_name]}")
            self.config[config_name] = value
            with open("usr/markov_config.json", "w") as file:
                json.dump(self.config, file)
        else:
            await ctx.send("Invalid config name")


async def setup(bot):
    await bot.add_cog(Markov(bot))
