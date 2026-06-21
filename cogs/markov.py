import json
import math
import random
import re
import unicodedata
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


DISCORD_EMOTE_RE = re.compile(r"<(?P<animated>a?):(?P<name>[a-zA-Z0-9_]+):(?P<id>\d+)>")
EMOJI_FORMAT_CHARS = {"\ufe0f", "\u200d"}
TWEMOJI_BASE_URL = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72"


def check_and_set_defaults(config):
    defaults = dict(state_size=1, tries=100, test_output=False, min_words=1, excluded_channels=[])

    for key, default_value in defaults.items():
        if key not in config:
            config[key] = default_value

    return config


def sanitize_meme_caption(text: str, fallback: str = "MIT MOND?") -> str:
    if not text:
        return fallback

    if re.search(r"[\u00c3\u00c2\u00e2\u00f0]", text):
        try:
            text = text.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

    text = DISCORD_EMOTE_RE.sub("", text)
    text = "".join(
        char
        for char in text
        if unicodedata.category(char)[0] not in {"C", "S"}
    )
    text = re.sub(r"\s+", " ", text).strip()

    if not re.search(r"[A-Za-z0-9\u00c0-\u017e]", text):
        return fallback
    return text


class Markov(commands.Cog):
    def __init__(self, bot):
        self.text_model = {}
        self.bot = bot
        self.emote_cache = {}
        self.emoji_font_cache = {}
        self.emoji_image_cache = {}

        # BOT_FRIENDS: comma-separated bot user IDs that are allowed to talk
        # to us. Every other bot stays ignored (no accidental loops with
        # random bots). Example: BOT_FRIENDS=1498350417074196621
        self.bot_friends = {
            int(x) for x in os.getenv("BOT_FRIENDS", "").replace(" ", "").split(",")
            if x.isdigit()
        }

        if not os.path.exists(f"usr/markov/"):
            os.mkdir(f"usr/markov/")
        try:
            with open("usr/markov_config.json", "r", encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = check_and_set_defaults({})
            with open("usr/markov_config.json", "w") as file:
                json.dump(self.config, file)
        self.config = check_and_set_defaults(self.config)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.content or message.guild is None:
            return
        if message.author.bot:
            # Bot-authored messages: only configured bot friends get through,
            # they can only TRIGGER a reply (mention or reply-to-us), and we
            # never learn their text into the markov corpus — that would let
            # two bots echo-train each other.
            if message.author.id not in self.bot_friends:
                return
            mentioned = f"<@{self.bot.user.id}>" in message.content
            replied_to_us = False
            if message.type == discord.MessageType.reply and message.reference:
                reference = await message.channel.fetch_message(
                    message.reference.message_id)
                replied_to_us = reference.author.id == self.bot.user.id
            if mentioned or replied_to_us:
                await self.markov(message)
            return
        if not os.path.exists(f"usr/markov//{message.guild.id}/"):
            os.mkdir(f"usr/markov//{message.guild.id}/")
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

            # Replying to a bot friend must actually PING it (reply pings are
            # off by default and main.py suppresses user mentions globally) —
            # mention-gated bots can't see our reply otherwise. Humans keep
            # the current no-ping behaviour.
            await ctx.reply(sentence if sentence else "MIT MOND?",
                            mention_author=getattr(ctx.author, "bot", False))
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
                text = sanitize_meme_caption(sentence)
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
            text1 = await self.make_sentence(ctx.guild.id, 10, fix_tags=True)
            text2 = await self.make_sentence(ctx.guild.id, 10, fix_tags=True)
            caption_layout = self.layout_demotivator_captions(draw, text1, text2)

            # Write text onto the template 466 , 511
            for i, line in enumerate(caption_layout["title_lines"]):
                y = caption_layout["title_y"] + i * caption_layout["title_line_height"]
                self.draw_rich_line(template, draw, line, 375, y, caption_layout["title_font"], "white")
            for i, line in enumerate(caption_layout["subtitle_lines"]):
                y = caption_layout["subtitle_y"] + i * caption_layout["subtitle_line_height"]
                self.draw_rich_line(template, draw, line, 375, y, caption_layout["subtitle_font"], "white")

            # Save the final image
            template.save("usr/demotivator.png")
            file = discord.File("usr/demotivator.png")
            await ctx.send(file=file)

        except Exception as e:
            print(f"baj van: {e}")
            await ctx.send(f"baj van: {e}")

    def clean_demotivator_caption(self, text: str) -> str:
        if not text:
            return "MIT MOND?"

        if re.search(r"[\u00c3\u00c2\u00e2\u00f0]", text):
            try:
                text = text.encode("cp1252").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        text = "".join(
            char
            for char in text
            if unicodedata.category(char) not in {"Cc", "Cs", "Cn"}
        )
        text = re.sub(r"\s+", " ", text).strip()
        return text or "MIT MOND?"

    def rich_text_units(self, text: str):
        text = self.clean_demotivator_caption(text)
        position = 0

        for match in DISCORD_EMOTE_RE.finditer(text):
            if match.start() > position:
                yield from self.plain_text_units(text[position:match.start()])

            yield {
                "type": "emote",
                "raw": match.group(0),
                "id": match.group("id"),
                "animated": bool(match.group("animated")),
            }
            position = match.end()

        if position < len(text):
            yield from self.plain_text_units(text[position:])

    @staticmethod
    def plain_text_units(text: str):
        for unit in re.findall(r"\S+|\s+", text):
            if unit.isspace():
                yield {"type": "space", "text": " "}
                continue

            current_type = None
            current_text = ""
            for char in unit:
                char_type = "emoji" if Markov.is_emoji_char(char) else "text"
                if current_type and char_type != current_type:
                    yield {"type": current_type, "text": current_text}
                    current_text = ""

                current_type = char_type
                current_text += char

            if current_text:
                yield {"type": current_type, "text": current_text}

    @staticmethod
    def is_emoji_char(char: str) -> bool:
        return unicodedata.category(char)[0] == "S" or char in {"\ufe0f", "\u200d"}

    def get_discord_emote(self, emote_id: str, animated: bool, height: int):
        cache_key = (emote_id, animated, height)
        if cache_key in self.emote_cache:
            return self.emote_cache[cache_key]

        extension = "gif" if animated else "png"
        url = f"https://cdn.discordapp.com/emojis/{emote_id}.{extension}"

        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            emote = Image.open(BytesIO(response.content))
            emote.seek(0)
            emote = emote.convert("RGBA")
            ratio = height / emote.height
            width = max(1, int(emote.width * ratio))
            emote = emote.resize((width, height), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Failed to load Discord emote {emote_id}: {e}")
            emote = None

        self.emote_cache[cache_key] = emote
        return emote

    @staticmethod
    def font_mask_signature(font, text: str):
        mask = font.getmask(text)
        return mask.size, bytes(mask)

    def font_supports_text(self, font, text: str) -> bool:
        try:
            missing_signature = self.font_mask_signature(font, "\uffff")
        except Exception:
            missing_signature = None

        for char in text:
            if char in EMOJI_FORMAT_CHARS:
                continue

            try:
                if font.getmask(char).getbbox() is None:
                    return False
                if missing_signature and self.font_mask_signature(font, char) == missing_signature:
                    return False
            except Exception:
                return False

        return True

    def get_emoji_fonts(self, size: int):
        if size in self.emoji_font_cache:
            return self.emoji_font_cache[size]

        emoji_fonts = []
        for font_path in (
            "C:/Windows/Fonts/seguiemj.ttf",
            "C:/Windows/Fonts/seguisym.ttf",
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
            "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
            "res/DejaVuSans.ttf",
        ):
            if not os.path.exists(font_path):
                continue

            try:
                emoji_fonts.append(ImageFont.truetype(font_path, size))
            except Exception:
                continue

        self.emoji_font_cache[size] = emoji_fonts
        return emoji_fonts

    def get_emoji_font(self, size: int, text: str):
        for emoji_font in self.get_emoji_fonts(size):
            if self.font_supports_text(emoji_font, text):
                return emoji_font

        return None

    def draw_text(self, draw, position, text: str, font, fill: str):
        try:
            draw.text(position, text, fill=fill, font=font, embedded_color=True)
        except TypeError:
            draw.text(position, text, fill=fill, font=font)

    @staticmethod
    def is_emoji_modifier(char: str) -> bool:
        codepoint = ord(char)
        return 0x1f3fb <= codepoint <= 0x1f3ff

    @staticmethod
    def is_regional_indicator(char: str) -> bool:
        codepoint = ord(char)
        return 0x1f1e6 <= codepoint <= 0x1f1ff

    @staticmethod
    def iter_emoji_clusters(text: str):
        index = 0
        while index < len(text):
            start = index
            index += 1

            if index < len(text) and text[index] == "\ufe0f":
                index += 1
            if index < len(text) and Markov.is_emoji_modifier(text[index]):
                index += 1
            if index < len(text) and text[index] == "\u20e3":
                index += 1

            if Markov.is_regional_indicator(text[start]) and index < len(text) and Markov.is_regional_indicator(text[index]):
                index += 1

            while index < len(text) and text[index] == "\u200d":
                index += 1
                if index >= len(text):
                    break
                index += 1
                if index < len(text) and text[index] == "\ufe0f":
                    index += 1
                if index < len(text) and Markov.is_emoji_modifier(text[index]):
                    index += 1

            yield text[start:index]

    @staticmethod
    def emoji_asset_key(sequence: str) -> str:
        return "-".join(f"{ord(char):x}" for char in sequence)

    @staticmethod
    def emoji_asset_key_candidates(sequence: str):
        candidates = [Markov.emoji_asset_key(sequence)]
        without_text_modifiers = sequence.replace("\ufe0f", "")
        if without_text_modifiers != sequence:
            candidates.append(Markov.emoji_asset_key(without_text_modifiers))
        return candidates

    def get_emoji_image(self, sequence: str, height: int):
        for asset_key in self.emoji_asset_key_candidates(sequence):
            cache_key = (asset_key, height)
            if cache_key in self.emoji_image_cache:
                emoji = self.emoji_image_cache[cache_key]
                if emoji:
                    return emoji
                continue

            try:
                response = requests.get(f"{TWEMOJI_BASE_URL}/{asset_key}.png", timeout=5)
                response.raise_for_status()
                emoji = Image.open(BytesIO(response.content)).convert("RGBA")
                ratio = height / emoji.height
                width = max(1, int(emoji.width * ratio))
                emoji = emoji.resize((width, height), Image.Resampling.LANCZOS)
            except Exception:
                emoji = None

            self.emoji_image_cache[cache_key] = emoji
            if emoji:
                return emoji

        return None

    def measure_emoji_text(self, text: str, font) -> float:
        width = 0
        for sequence in self.iter_emoji_clusters(text):
            emoji = self.get_emoji_image(sequence, font.size)
            if emoji:
                width += emoji.width + 2
                continue

            emoji_font = self.get_emoji_font(font.size, sequence) or font
            width += emoji_font.getlength(sequence)

        return width

    def draw_emoji_text(self, image, draw, text: str, x: float, y: float, font, fill: str) -> float:
        for sequence in self.iter_emoji_clusters(text):
            emoji = self.get_emoji_image(sequence, font.size)
            if emoji:
                image.paste(emoji, (round(x), round(y)), emoji)
                x += emoji.width + 2
                continue

            emoji_font = self.get_emoji_font(font.size, sequence) or font
            self.draw_text(draw, (x, y), sequence, emoji_font, fill)
            x += emoji_font.getlength(sequence)

        return x

    def measure_rich_unit(self, unit, font):
        if unit["type"] == "emote":
            emote = self.get_discord_emote(unit["id"], unit["animated"], font.size)
            return emote.width + 4 if emote else 0

        if unit["type"] == "emoji":
            return self.measure_emoji_text(unit["text"], font)

        return font.getlength(unit["text"])

    def layout_demotivator_captions(self, draw, title: str, subtitle: str):
        caption_top = 455
        caption_bottom = 596
        caption_height = caption_bottom - caption_top
        min_gap = 8
        title_font = ImageFont.truetype("res/DejaVuSans.ttf", 45)
        subtitle_font = ImageFont.truetype("res/DejaVuSans.ttf", 30)
        title_lines = self.wrap_rich_text(title, title_font, max_width=650)
        subtitle_lines = self.wrap_rich_text(subtitle, subtitle_font, max_width=650)

        if len(title_lines) > 1 or len(subtitle_lines) > 1:
            title_font = ImageFont.truetype("res/DejaVuSans.ttf", 32)
            subtitle_font = ImageFont.truetype("res/DejaVuSans.ttf", 21)
            title_lines = self.wrap_rich_text(title, title_font, max_width=650)
            subtitle_lines = self.wrap_rich_text(subtitle, subtitle_font, max_width=650)

        title_line_height = self.rich_line_height(draw, title_font)
        subtitle_line_height = self.rich_line_height(draw, subtitle_font)
        title_height = len(title_lines) * title_line_height
        subtitle_height = len(subtitle_lines) * subtitle_line_height
        total_height = title_height + min_gap + subtitle_height
        start_y = caption_top + max(0, (caption_height - total_height) // 2)

        return {
            "title_font": title_font,
            "subtitle_font": subtitle_font,
            "title_lines": title_lines,
            "subtitle_lines": subtitle_lines,
            "title_line_height": title_line_height,
            "subtitle_line_height": subtitle_line_height,
            "title_y": start_y,
            "subtitle_y": start_y + title_height + min_gap,
        }

    @staticmethod
    def rich_line_height(draw, font):
        bbox = draw.textbbox((0, 0), "Ág", font=font)
        return (bbox[3] - bbox[1]) + 4

    def wrap_rich_text(self, text: str, font, max_width: int):
        lines = []
        current_line = []
        current_width = 0

        for unit in self.rich_text_units(text):
            if unit["type"] == "space" and not current_line:
                continue

            unit_width = self.measure_rich_unit(unit, font)
            if current_line and current_width + unit_width > max_width:
                while current_line and current_line[-1]["type"] == "space":
                    current_width -= self.measure_rich_unit(current_line.pop(), font)

                lines.append(current_line)
                current_line = []
                current_width = 0

                if unit["type"] == "space":
                    continue

            current_line.append(unit)
            current_width += unit_width

        while current_line and current_line[-1]["type"] == "space":
            current_line.pop()

        if current_line:
            lines.append(current_line)

        if not lines:
            return self.wrap_rich_text("MIT MOND?", font, max_width)

        return lines

    def draw_rich_line(self, image, draw, line, center_x: int, y: int, font, fill: str):
        total_width = sum(self.measure_rich_unit(unit, font) for unit in line)
        x = center_x - total_width / 2

        for unit in line:
            if unit["type"] == "emote":
                emote = self.get_discord_emote(unit["id"], unit["animated"], font.size)
                if emote:
                    image.paste(emote, (round(x), round(y)), emote)
                    x += emote.width + 4
                    continue

                continue
            else:
                if unit["type"] == "emoji":
                    x = self.draw_emoji_text(image, draw, unit["text"], x, y, font, fill)
                    continue

                text_font = self.get_emoji_font(font.size, unit["text"]) if unit["type"] == "emoji" else font
                text_font = text_font or font
                self.draw_text(draw, (x, y), unit["text"], text_font, fill)
                x += text_font.getlength(unit["text"])

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
            emote_pattern = DISCORD_EMOTE_RE
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
