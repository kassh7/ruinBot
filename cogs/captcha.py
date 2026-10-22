import asyncio
import glob
import logging
import math
import os
import random
import re
import time
from io import BytesIO

import discord
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands

log = logging.getLogger(__name__)

FONT_PATH = "res/DejaVuSans.ttf"
FONT_SIZE = 42
MARKOV_GLOB = "usr/markov/*/*.txt"
WORD_CACHE_SECONDS = 300

# stuff in the markov corpus that should never end up as a captcha word
STRIP_RE = re.compile(r"https?://\S+|<a?:\w+:\d+>|<[@#][!&]?\d+>")
WORD_RE = re.compile(r"^[a-zà-žA-ZÀ-Ž]{3,12}$")
PUNCT = ".,!?;:\"'()[]{}*_~`-"


class Captcha(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
        self.words = []
        self.words_expiry = 0.0

    @staticmethod
    def load_words() -> list[str]:
        """Collect every usable word from all servers' markov files."""
        words = set()
        for path in glob.glob(MARKOV_GLOB):
            if os.path.basename(path) == "urls.txt":
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    for word in STRIP_RE.sub(" ", line).split():
                        word = word.strip(PUNCT).lower()
                        if WORD_RE.match(word):
                            words.add(word)
        return list(words)

    async def get_words(self) -> list[str]:
        if time.time() > self.words_expiry:
            self.words = await asyncio.to_thread(self.load_words)
            self.words_expiry = time.time() + WORD_CACHE_SECONDS
        return self.words

    def render(self, text: str) -> bytes:
        """Draw black, wobbly, crossed-out text on a white background."""
        ascent, descent = self.font.getmetrics()
        tile_size = ascent + descent + 20
        pad = 20
        width = int(self.font.getlength(text) * 0.95) + pad * 2
        height = tile_size + pad
        image = Image.new("RGB", (width, height), "white")

        # each letter gets its own rotation and vertical jitter
        x = pad
        for char in text:
            advance = self.font.getlength(char)
            if char != " ":
                tile = Image.new("L", (tile_size, tile_size), 0)
                ImageDraw.Draw(tile).text((10, 10), char, font=self.font, fill=255)
                tile = tile.rotate(random.uniform(-22, 22), resample=Image.BICUBIC)
                y = pad // 2 + random.randint(-5, 5)
                image.paste("black", (int(x) - 10, y - 10), tile)
            # letters squish into each other a little
            x += advance * random.uniform(0.85, 1.0)

        draw = ImageDraw.Draw(image)
        # long wavy strikes through the text
        for _ in range(random.randint(2, 3)):
            y0 = pad // 2 + random.uniform(ascent * 0.45, ascent * 0.95)
            amplitude = random.uniform(3, 10)
            frequency = random.uniform(0.01, 0.04)
            phase = random.uniform(0, math.tau)
            slope = random.uniform(-0.08, 0.08)
            start = random.randint(0, width // 4)
            end = random.randint(width * 3 // 4, width)
            points = [
                (px, y0 + slope * (px - start) + amplitude * math.sin(px * frequency + phase))
                for px in range(start, end, 4)
            ]
            draw.line(points, fill="black", width=random.randint(2, 3), joint="curve")
        # short stray scratches
        for _ in range(random.randint(2, 5)):
            sx, sy = random.randint(0, width), random.randint(0, height)
            draw.line(
                [(sx, sy), (sx + random.randint(-30, 30), sy + random.randint(-15, 15))],
                fill="black",
                width=2,
            )

        out = BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()

    @commands.hybrid_command(
        name="captcha",
        with_app_command=True,
        description="dob egy rare captchát",
    )
    @commands.cooldown(rate=1, per=2.0, type=commands.BucketType.user)
    async def captcha(self, ctx):
        words = await self.get_words()
        if len(words) < 2:
            await ctx.reply("baj van: még nincs elég szó a markov adatbázisban")
            return
        text = " ".join(random.sample(words, 2))
        data = await asyncio.to_thread(self.render, text)
        await ctx.reply(file=discord.File(BytesIO(data), filename="captcha.png"))

    @captcha.error
    async def captcha_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"várjál már xd próbáld meg {error.retry_after:.1f} mp múlva")
        else:
            log.exception("unhandled error in /captcha")
            await ctx.reply("baj van: a captcha nem működik most")


async def setup(bot):
    await bot.add_cog(Captcha(bot))
