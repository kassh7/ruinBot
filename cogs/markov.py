import json
import random
import re
from random import randint

import discord
import os

import requests
from discord import app_commands
from discord.ext import commands
import markovify


def check_and_set_defaults(config):
    defaults = dict(state_size=1, tries=100, test_output=False, min_words=1)

    for key, default_value in defaults.items():
        if key not in config:
            config[key] = default_value

    return config


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
            self.config = check_and_set_defaults([])
            with open("usr/markov_config.json", "w") as file:
                json.dump(self.config, file)
        self.config = check_and_set_defaults(self.config)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.content:
            return
        if f"<@{self.bot.user.id}>" in message.content:
            await self.markov(message)

        if message.type == discord.MessageType.reply:
            reference = await message.channel.fetch_message(
                message.reference.message_id)

            if reference.author.id == self.bot.user.id:
                await self.markov(message)
        start_filters = ("$", "r!", "<@1197841378961543198>", "<@1194709611077435466>")
        if message.content.startswith(start_filters):
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
    @app_commands.describe(config_name='state_size or tries')
    async def markov_config(self, ctx, config_name: str, value: int):
        if config_name in ("state_size", "tries"):
            await ctx.send(f"{config_name} changed to {value} from {self.config[config_name]}")
            self.config[config_name] = value
            with open("usr/markov_config.json", "w") as file:
                json.dump(self.config, file)
        else:
            await ctx.send("Invalid config name")

    @commands.hybrid_command(name="markovpic", with_app_command=True,
                             description="Generates an image with generated text")
    async def markov_pic(self, ctx):
        try:
            text = ""
            for filename in os.listdir("usr/markov/"):
                with open(os.path.join("usr/markov/", filename), 'r', encoding='utf-8') as f:
                    if filename == "urls.txt":
                        continue
                    else:
                        text = text + f.read()

            if not self.text_model:
                self.text_model = markovify.NewlineText(text, state_size=self.config["state_size"])

            boxes = []
            r = requests.get("https://api.imgflip.com/get_memes")
            memes = r.json()
            meme_num = randint(0, 99)
            meme = memes["data"]["memes"][meme_num]
            post_json = {
                "template_id": meme["id"],
                "username": os.getenv("IMGFLIP_USER"),
                "password": os.getenv("IMGFLIP_PASS"),
            }
            for x in range(meme['box_count']):
                sentence = self.text_model.make_sentence(tries=self.config["tries"])
                # replace tags with names because images
                pattern = r'<@(\d{17,18})>' # matches discord tags
                matches = re.findall(pattern, sentence)
                for match in matches:
                    print(match)
                    username = self.bot.get_user(int(match)).display_name
                    sentence = sentence.replace(f'<@{match}>', str(username))
                post_json.update({"boxes[{}][text]".format(x): sentence if sentence else "MIT MOND?"})

            r = requests.post("https://api.imgflip.com/caption_image", data=post_json)
            meme_pic = r.json()
            if meme_pic["success"]:
                await ctx.reply(meme_pic["data"]["url"])
            else:
                await ctx.reply(f"imgflip szar: \n {meme_pic['error_message']}")

        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")


async def setup(bot):
    await bot.add_cog(Markov(bot))
