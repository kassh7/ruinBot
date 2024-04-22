import json
import random
import re
import textwrap
from io import BytesIO
from random import randint
from PIL import Image, ImageDraw, ImageFont

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
            await self.markov(message, seed=message.content)

        if message.type == discord.MessageType.reply:
            reference = await message.channel.fetch_message(
                message.reference.message_id)

            if reference.author.id == self.bot.user.id:
                await self.markov(message)
        start_filters = ("$", "r!", "<@1197841378961543198>", "<@1194709611077435466>", "!", ".")
        if message.content.startswith(start_filters):
            return

        # Regular expression to match URLs
        url_pattern = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+')

        # Check if the string contains a URL
        if re.search(url_pattern, message.content):
            embeds = [".gif", ".mp4", ".png", ".gif", ".gifv", ".webm", ".jpg", ".jpeg", "tenor.com"]
            if any(ext in message.content for ext in embeds):
                with open(f"usr/markov/urls.txt", "a", encoding='utf-8') as f:
                    f.write(message.content + "\n")
            return

        with open(f"usr/markov/{message.channel}.txt", "a", encoding='utf-8') as f:
            f.write(message.content + "\n")

    @commands.command(aliases=['mark'])
    async def markov(self, ctx, seed=None):
        try:
            with open("usr/markov/urls.txt", 'r', encoding='utf-8') as f:
                urls = f.readlines()

            chance = randint(1, 100)
            if chance > 10:
                sentence = await self.make_sentence()
            else:
                sentence = random.choice(urls)

            await ctx.reply(sentence if sentence else "MIT MOND?")
        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

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
                sentence = await self.make_sentence(10, True)
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

    @commands.hybrid_command(name="demotivator", with_app_command=True,
                             description="demotiváló nukáló")
    async def demotivator(self, ctx, user: discord.Member = None):
        try:
            if user is None:
                user = random.choice(ctx.channel.members)
            response = requests.get(user.display_avatar.with_format('png').url)
            image = Image.open(BytesIO(response.content))
            template = Image.open("res/demotivator_template.png")
            resized_image = image.resize((600, 400))

            # Calculate the position to place the image
            x_offset = 75
            y_offset = 50

            # Paste the image onto the template
            template.paste(resized_image, (x_offset, y_offset))

            # Add text
            draw = ImageDraw.Draw(template)
            font1 = ImageFont.truetype("arial.ttf", 45)
            font2 = ImageFont.truetype("arial.ttf", 30)
            text1 = await self.make_sentence(10, fix_tags=True)
            text2 = await self.make_sentence(10, fix_tags=True)
            lines1 = textwrap.wrap(text1, width=30)
            lines2 = textwrap.wrap(text2, width=45)

            text1_y = 470 if len(lines1) is 1 else 455
            text2_y = 540 if len(lines2) is 1 else 530

            # Write text onto the template 466 , 511
            for i in range(len(lines1)):
                text1_x = 375 - font1.getlength(lines1[i]) // 2
                draw.multiline_text((text1_x, text1_y+i*35), lines1[i], fill="white", font=font1, align="center")
            for i in range(len(lines2)):
                text2_x = 375 - font2.getlength(lines2[i]) // 2
                draw.multiline_text((text2_x, text2_y+i*35), lines2[i], fill="white", font=font2, align="center")

            # Save the final image
            template.save("usr/demotivator.png")
            file = discord.File("usr/demotivator.png")
            await ctx.send(file=file)

        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    async def make_sentence(self, max_words: int = None, fix_tags: bool = False):
        text = ""
        for filename in os.listdir("usr/markov/"):
            with open(os.path.join("usr/markov/", filename), 'r', encoding='utf-8') as f:
                if filename == "urls.txt":
                    continue
                else:
                    print(filename)
                    text = text + f.read()

        if not self.text_model:
            self.text_model = markovify.NewlineText(text, state_size=self.config["state_size"])
        sentence = self.text_model.make_sentence(tries=self.config["tries"],
                                                 test_output=self.config["test_output"],
                                                 min_words=self.config["min_words"], max_words=max_words)
        if fix_tags:
            # replace tags with names because images
            pattern = r'<@(\d{17,18})>'  # matches discord tags
            matches = re.findall(pattern, sentence)
            for match in matches:
                if self.bot.get_user(int(match)) is None:
                    username = "orbán"
                else:
                    username = self.bot.get_user(int(match)).display_name

                sentence = sentence.replace(f'<@{match}>', str(username))
            return sentence
        else:
            return sentence


async def setup(bot):
    await bot.add_cog(Markov(bot))
