import logging
import re
from io import BytesIO

import aiohttp
import discord
from PIL import Image
from discord.ext import commands

log = logging.getLogger(__name__)

MUVELET_URL = (
    "https://hardverapro.hu/muvelet/tag/uj.php"
    "?url=%2Fmuvelet%2Fhozzaferes%2Fbelepes.php%3Furl%3D%252Findex.html"
)
HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "en-US,en;q=0.9",
    "referer": "https://hardverapro.hu/index.html",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
    "x-requested-with": "XMLHttpRequest",
}
# matches both "/captcha/file.png" and JSON-escaped "\/captcha\/file.png"
CAPTCHA_PATH_RE = re.compile(r'\\?/captcha\\?/([^"\\]+\.png)')


class CaptchaError(Exception):
    pass


class Captcha(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get(self, url):
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.read()

    async def fetch_captcha_url(self) -> str:
        text = (await self._get(MUVELET_URL)).decode("utf-8", "replace")
        match = CAPTCHA_PATH_RE.search(text)
        if not match:
            raise CaptchaError("a hardverapro.hu nem adott captcha url-t")
        return f"https://hardverapro.hu/captcha/{match.group(1)}"

    @staticmethod
    def on_white(data: bytes) -> bytes:
        # the hardvera captcha is a transparent PNG with black text — unreadable
        # on dark discord, so composite it onto a white background
        img = Image.open(BytesIO(data)).convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        composited = Image.alpha_composite(background, img)
        out = BytesIO()
        composited.save(out, format="PNG")
        return out.getvalue()

    @commands.hybrid_command(
        name="captcha",
        with_app_command=True,
        description="dob egy rare captchát",
    )
    @commands.cooldown(rate=1, per=2.0, type=commands.BucketType.user)
    async def captcha(self, ctx):
        await ctx.defer()
        try:
            url = await self.fetch_captcha_url()
            data = await self._get(url)
            data = self.on_white(data)
        except (aiohttp.ClientError, CaptchaError, Image.UnidentifiedImageError) as e:
            log.exception("captcha request failed")
            await ctx.reply(f"baj van: nem sikerült lekérni a captchát ({e})")
            return
        await ctx.reply(file=discord.File(BytesIO(data), filename="hardvera_captcha.png"))

    @captcha.error
    async def captcha_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"várjál már xd próbáld meg {error.retry_after:.1f} mp múlva")
        else:
            log.exception("unhandled error in /captcha")
            await ctx.reply("baj van: a captcha nem működik most")


async def setup(bot):
    await bot.add_cog(Captcha(bot))
