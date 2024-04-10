import discord
import os
from discord.ext import commands
import markovify


class Markov(commands.Cog):
    def __init__(self, bot):
        self.text_model = None
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.content or message.content.startswith("$") or message.content.startswith("r!"):
            return

        if not os.path.exists("usr/markov/"):
            os.mkdir("usr/markov/")

        with open(f"usr/markov/{message.channel}.txt", "a", encoding='utf-8') as f:
            f.write(message.content + "\n")

    @commands.command(aliases=['mark'])
    async def markov(self, ctx):
        text = ""
        for filename in os.listdir("usr/markov/"):
            with open(os.path.join("usr/markov/", filename), 'r', encoding='utf-8') as f:
                print(filename)
                text = text+f.read()

        if not self.text_model:
            self.text_model = markovify.NewlineText(text)

        sentence = self.text_model.make_sentence()

        await ctx.send(sentence if sentence else "MIT MOND?")


async def setup(bot):
    await bot.add_cog(Markov(bot))
