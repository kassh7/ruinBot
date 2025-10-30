import json
import math
import random
import re
import textwrap
from datetime import datetime, timedelta
from io import BytesIO
from random import randint
from PIL import Image, ImageDraw, ImageFont
from typing import Union
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import discord
import os

import requests
from discord import app_commands
from discord.ext import commands
import markovify


def check_and_set_defaults(config):
    defaults = dict(state_size=1, tries=100, test_output=False, min_words=1, excluded_channels=[])

    for key, default_value in defaults.items():
        if key not in config:
            config[key] = default_value

    return config


class Markov(commands.Cog):
    def __init__(self, bot):
        self.text_model = {}
        self.bot = bot

        if not os.path.exists(f"usr/markov/"):
            os.mkdir(f"usr/markov/")
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
        if not os.path.exists(f"usr/markov//{message.guild.id}/"):
            os.mkdir(f"usr/markov//{message.guild.id}/")
        if message.author.bot or not message.content:
            return
        if f"<@{self.bot.user.id}>" in message.content:
            if f"<@{self.bot.user.id}> ^" in message.content:
                seed = message.content.replace(f"<@{self.bot.user.id}> ^", "")
                await self.markov(message, seed=seed)
            else:
                await self.markov(message)

        if message.type == discord.MessageType.reply:
            reference = await message.channel.fetch_message(
                message.reference.message_id)

            if reference.author.id == self.bot.user.id:
                await self.markov(message)
        start_filters = ("$", "r!", "<@1197841378961543198>", "<@1194709611077435466>", "!", ".")
        if message.content.startswith(start_filters):
            return
        if '||' in message.content:
            return
        if message.channel.id in self.config["excluded_channels"]:
            return

        # Regular expression to match URLs
        url_pattern = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+')

        # Check if the string contains a URL
        if re.search(url_pattern, message.content):
            embeds = [".gif", ".mp4", ".png", ".gif", ".gifv", ".webm", ".jpg", ".jpeg", "tenor.com"]
            if any(ext in message.content for ext in embeds):
                with open(f"usr/markov/{message.guild.id}/urls.txt", "a", encoding='utf-8') as f:
                    f.write(message.content + "\n")
            return

        with open(f"usr/markov/{message.guild.id}/{message.channel.id}.txt", "a", encoding='utf-8') as f:
            f.write(message.content + "\n")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Removes a URL from urls.txt if a user with admin rights reacts with ❌."""
        if user.bot:
            return

        message = reaction.message

        # Ensure the bot sent the message
        if message.author != self.bot.user:
            return  # Exit early if it's not the bot's message

        if reaction.emoji == "❌":
            message = reaction.message

            # URL detection regex
            url_pattern = re.compile(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+")
            match = re.search(url_pattern, message.content)

            if match:
                url = match.group()
                urls_file = f"usr/markov/{message.guild.id}/urls.txt"

                # Check if the user has administrator permissions
                if not user.guild_permissions.administrator:
                    return

                if os.path.exists(urls_file):
                    with open(urls_file, "r", encoding="utf-8") as f:
                        urls = f.readlines()
                    if not any(message.content in line for line in urls):
                        return

                    # Remove the specific URL
                    new_urls = [line for line in urls if message.content not in line]

                    # Save the updated file
                    with open(urls_file, "w", encoding="utf-8") as f:
                        f.writelines(new_urls)

                    await message.channel.send(f"✅ URL removed by {user.mention}", delete_after=5)

    @commands.hybrid_command(aliases=['mark'])
    async def markov(self, ctx, seed=None):
        try:
            with open(f"usr/markov/{ctx.guild.id}/urls.txt", 'r', encoding='utf-8') as f:
                urls = f.readlines()

            chance = randint(1, 100)
            sentence = None

            # If a seed is provided, use it to steer generation.
            # Convention:
            #   - seed starts with '^'  -> force sentence to start with the remainder
            #   - otherwise             -> sentence must include the seed somewhere
            if seed:
                print(f"seed gen")
                seed = seed.strip()
                sentence = await self.make_sentence(ctx.guild.id, start_with=seed)
            else:
                print(f"no seed gen")
                if chance > 10 or not urls:
                    sentence = await self.make_sentence(ctx.guild.id)
                else:
                    sentence = random.choice(urls).strip()

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

    @commands.hybrid_command(name="exclude_list", with_app_command=True,
                             description="modifies the exclusion list from markov generation")
    @app_commands.describe(channel="The text channel to modify", command="Choose an action: add, list, or remove")
    @app_commands.choices(command=[app_commands.Choice(name="add", value="add"),
                                   app_commands.Choice(name="list", value="list"),
                                   app_commands.Choice(name="remove", value="remove")])
    async def exclude_list(self, ctx: commands.Context, command: app_commands.Choice[str],
                           channel: Union[discord.TextChannel, discord.Thread] = None):
        if command.value == "add":
            if channel is None:
                await ctx.send("❌ Please specify a channel to add.")
                return
            if channel.id not in self.config["excluded_channels"]:
                self.config["excluded_channels"].append(channel.id)
                await ctx.send(f"✅ Channel {channel.mention} added to the exclusion list.")
                with open("usr/markov_config.json", "w") as file:
                    json.dump(self.config, file)
            else:
                await ctx.send(f"⚠️ Channel {channel.mention} is already in the exclusion list.")

        elif command.value == "remove":
            if channel is None:
                await ctx.send("❌ Please specify a channel to remove.")
                return
            if channel.id in self.config["excluded_channels"]:
                self.config["excluded_channels"].remove(channel.id)
                await ctx.send(f"✅ Channel {channel.mention} removed from the exclusion list.")
                with open("usr/markov_config.json", "w") as file:
                    json.dump(self.config, file)
            else:
                await ctx.send(f"⚠️ Channel {channel.mention} is not in the exclusion list.")

        elif command.value == "list":
            if self.config["excluded_channels"]:
                excluded = [
                    f"<#{chan_id}>" for chan_id in self.config["excluded_channels"]
                ]
                await ctx.send(f"📜 Exclusion list:\n{', '.join(excluded)}")
            else:
                await ctx.send("ℹ️ The exclusion list is currently empty.")

        else:
            await ctx.send("❌ Invalid command!")

    @commands.hybrid_command(name="markovpic", with_app_command=True,
                             description="Generates an image with generated text")
    async def markov_pic(self, ctx, seed: str = None):
        try:
            if ctx.interaction:
                await ctx.interaction.response.defer()

            # Create a session with retry behavior
            session = requests.Session()
            retries = Retry(
                total=5,  # total number of retries
                backoff_factor=2,  # wait 2, 4, 8, ... seconds between retries
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
            )
            adapter = HTTPAdapter(max_retries=retries)
            session.mount("https://", adapter)
            session.mount("http://", adapter)

            # Try to get the memes with a timeout
            r = session.get("https://api.imgflip.com/get_memes", timeout=10)
            r.raise_for_status()  # Will raise an HTTPError if the status is not 200
            memes = r.json()

            meme_num = randint(0, 99)
            meme = memes["data"]["memes"][meme_num]
            post_json = {
                "template_id": meme["id"],
                "username": os.getenv("IMGFLIP_USER"),
                "password": os.getenv("IMGFLIP_PASS"),
            }
            seed_box = randint(0, meme["box_count"] - 1)
            for x in range(meme["box_count"]):
                if seed and x == seed_box:
                    print(f"seed gen")
                    seed = seed.strip()
                    sentence = await self.make_sentence(ctx.guild.id, start_with=seed, max_words=10, fix_tags=True,
                                                        no_emotes=True)
                else:
                    sentence = await self.make_sentence(ctx.guild.id, 10, True, True)
                # Provide a default sentence if none is returned
                text = sentence if sentence else "MIT MOND?"
                post_json[f"boxes[{x}][text]"] = text

            # Post to imgflip API to generate the meme image
            r = session.post("https://api.imgflip.com/caption_image", data=post_json, timeout=10)
            r.raise_for_status()
            meme_pic = r.json()

            if meme_pic["success"]:
                await ctx.reply(meme_pic["data"]["url"])
            else:
                await ctx.reply(f"Imgflip returned an error:\n{meme_pic.get('error_message', 'Unknown error')}")

        except requests.exceptions.RequestException as req_err:
            # This block catches network related errors (including retries exhausted)
            error_message = (
                "There was a network error contacting the Imgflip API. "
                "Please try again later."
            )
            await ctx.reply(error_message)
            print(f"Network error: {req_err}")
        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    @commands.hybrid_command(name="demotivator", with_app_command=True,
                             description="demotiváló nukáló")
    async def demotivator(self, ctx, user: discord.Member = None, image_url: str = None):
        try:
            if ctx.interaction:
                await ctx.interaction.response.defer()
            if image_url:
                response = requests.get(image_url, stream=True)

                content_type = response.headers.get("Content-Type")
                if response.status_code == 200 and content_type and content_type.startswith("image/"):
                    image_data = response.content
                else:
                    await ctx.send("A megadott URL nem kép vagy nem érhető el.")
                    return
            else:
                if user is None:
                    user = random.choice(ctx.channel.members)

                response = requests.get(user.display_avatar.with_format('png').url)

                if response.status_code == 200:
                    image_data = response.content
                else:
                    await ctx.send("Nem sikerült letölteni a felhasználó avatarját.")
                    return
            image = Image.open(BytesIO(image_data))
            template = Image.open("res/demotivator_template.png")
            resized_image = image.resize((600, 400))

            # Calculate the position to place the image
            x_offset = 75
            y_offset = 50

            # Paste the image onto the template
            template.paste(resized_image, (x_offset, y_offset))

            # Add text
            draw = ImageDraw.Draw(template)
            font1 = ImageFont.truetype("res/DejaVuSans.ttf", 45)
            font2 = ImageFont.truetype("res/DejaVuSans.ttf", 30)
            text1 = await self.make_sentence(ctx.guild.id, 10, fix_tags=True, no_emotes=True)
            text2 = await self.make_sentence(ctx.guild.id, 10, fix_tags=True, no_emotes=True)
            lines1 = textwrap.wrap(text1, width=30)
            lines2 = textwrap.wrap(text2, width=45)

            text1_y = 470 if len(lines1) == 1 else 455
            text2_y = 540 if len(lines2) == 1 else 530

            # Write text onto the template 466 , 511
            for i in range(len(lines1)):
                text1_x = 375 - font1.getlength(lines1[i]) // 2
                draw.multiline_text((text1_x, text1_y + i * 35), lines1[i], fill="white", font=font1, align="center")
            for i in range(len(lines2)):
                text2_x = 375 - font2.getlength(lines2[i]) // 2
                draw.multiline_text((text2_x, text2_y + i * 35), lines2[i], fill="white", font=font2, align="center")

            # Save the final image
            template.save("usr/demotivator.png")
            file = discord.File("usr/demotivator.png")
            await ctx.send(file=file)

        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    @commands.hybrid_command(name="check_logs", with_app_command=True,
                             description="megmondja mekkorák a fileok")
    async def check_file_sizes(self, ctx):
        try:
            files = {}
            for filename in os.listdir(f"usr/markov/{ctx.guild.id}/"):
                files[filename] = os.path.getsize(f"usr/markov/{ctx.guild.id}/{filename}")
            field = ""
            for filename, size in files.items():
                channel_id = filename.replace(".txt", "")
                if channel_id.isdigit():
                    field += f"<#{channel_id}> - {math.ceil(size / 1000)} KB\n"
                else:
                    field += f"{filename} - {math.ceil(size / 1000)} KB\n"

            await ctx.send(field)

        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    async def make_sentence(self, guild_id: int, max_words: int = None, fix_tags: bool = False, no_emotes: bool = False,
                            start_with: str = None):
        text = ""
        sentence = None
        for filename in os.listdir(f"usr/markov/{guild_id}/"):
            with open(os.path.join(f"usr/markov/{guild_id}/", filename), 'r', encoding='utf-8') as f:
                if filename == "urls.txt":
                    continue
                else:
                    text = text + f.read()

        if guild_id not in self.text_model or self.text_model[guild_id]['expiry'] < datetime.now().timestamp():
            print(f"Generating new model for guild {guild_id}...")
            self.text_model[guild_id] = {
                "model": markovify.NewlineText(text, state_size=self.config["state_size"]),
                "expiry": (datetime.now() + timedelta(minutes=5)).timestamp()  # Set expiry to 5 minutes from now
            }
        model = self.text_model[guild_id]["model"]
        if start_with:
            # markovify requires the start length to match state_size if strict=True.
            # If your state_size > 1, users can pass multiple words like "hello there".
            try:
                sentence = model.make_sentence_with_start(
                    start_with,
                    strict=True,
                    max_words=max_words,
                    tries=self.config["tries"]
                )
            except Exception:
                sentence = None  # fall through to regular attempts if it fails

            # 3) If no start_with or it failed, do normal / must-include generation
        if sentence is None:
            sentence = self.text_model[guild_id]["model"].make_sentence(tries=self.config["tries"],
                                                                        test_output=self.config["test_output"],
                                                                        min_words=self.config["min_words"],
                                                                        max_words=max_words)
        if fix_tags:
            # Replace user, channel, and role tags with their names
            pattern = r'(<@!?\d+>|<#\d+>|<@&\d+>)'

            def replacer(match):
                mention = match.group(0)
                if mention.startswith("<@&"):  # Role mention
                    role_id = int(mention.strip("<@&>"))
                    for guild in self.bot.guilds:
                        role = guild.get_role(role_id)
                        if role is not None:
                            return role.name
                    return "fidesz"
                elif mention.startswith("<#"):  # Channel mention
                    channel_id = int(mention.strip("<#>"))
                    channel = self.bot.get_channel(channel_id)
                    return channel.name if channel is not None else "#karmelita"
                else:  # User mention
                    user_id = int(mention.strip("<@!>"))
                    user = self.bot.get_user(user_id)
                    return user.display_name if user is not None else "orbán"

            sentence = re.sub(pattern, replacer, sentence)

        if no_emotes:
            emote_pattern = r"<(?:a:)?[a-zA-Z0-9_]+:\d+>"
            while re.search(emote_pattern, sentence):
                print(f"emote detected {sentence}")
                # Remove the emote-like substring(s)
                sentence = self.text_model[guild_id]["model"].make_sentence(tries=self.config["tries"],
                                                                            test_output=self.config["test_output"],
                                                                            min_words=self.config["min_words"],
                                                                            max_words=max_words)

        return sentence


async def setup(bot):
    await bot.add_cog(Markov(bot))
