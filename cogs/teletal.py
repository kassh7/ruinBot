import discord
from discord.ext import commands, tasks
import asyncio
import json
import os
from datetime import datetime, timedelta
from cogs.holiday_cache import get_last_workday

CONFIG_FILE = "teletal_config.json"

class teletalReminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = self.load_config()
        self.teletal_loop.start()

    def cog_unload(self):
        self.teletal_loop.cancel()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        return {}

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=4)

    # --- CONFIGURATION COMMANDS ---

    teletal = discord.app_commands.Group(
        name="teletal",
        description="Teletál reminder konfiguráció",
        default_permissions=discord.Permissions(manage_guild=True)
    )

    @teletal.command(name="setup", description="Beállítja a teletál reminder funkciót.")
    @discord.app_commands.describe(
        channel="Ahova küldi az emlékeztetőt",
        role="Amelyik role-t pingeli (pl @teletál)",
        hour="Melyik órában küldjön ELŐSZÖR emlékeztetőt (0-23)",
        amount="Hány egymást követő órában nyaggatja őket (pl. 2 = 16:00 ÉS 17:00)"
    )
    async def setup_teletal(self, interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role, hour: int, amount: int = 1):
        if hour < 0 or hour > 23:
            await interaction.response.send_message("❌ Legyen már 0-23 közt az óra plz...", ephemeral=True)
            return

        safe_amount = max(1, min(amount, 5))
        guild_id = str(interaction.guild.id)
        self.config[guild_id] = {
            "channel_id": channel.id,
            "role_id": role.id,
            "hour": hour,
            "amount": safe_amount
        }
        self.save_config()

        end_hour = (hour + safe_amount - 1) % 24
        if safe_amount == 1:
            time_str = f"{hour}:00-kor"
        else:
            time_str = f"{hour}:00-tól {end_hour}:00-ig"

        await interaction.response.send_message(
            f"✅ Teletál reminder beállítva! Pingelem: {role.mention}, ide: {channel.mention}, {time_str}, minden hét utolsó munkanapján.",
            ephemeral=True
        )

    @teletal.command(name="disable", description="Kikapcsolja a teletál remindert a szerveren.")
    async def disable_teletal(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        if guild_id in self.config:
            del self.config[guild_id]
            self.save_config()
            await interaction.response.send_message("🛑 Teletál reminder kikapcsolva.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Eddig sem volt reminder helo!", ephemeral=True)

    @teletal.command(name="test", description="Teszt üzenet küldése, hogy lássuk működik-e.")
    async def test_teletal(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.config:
            await interaction.response.send_message("❌ Előbb futtasd a `/teletal setup`-ot!", ephemeral=True)
            return

        cfg = self.config[guild_id]
        channel = self.bot.get_channel(cfg["channel_id"])

        if not channel:
            await interaction.response.send_message("baj van: nem találom a csatornát!", ephemeral=True)
            return

        role_mention = f"<@&{cfg['role_id']}>"
        message = f"🍔🍟 {role_mention} **[TESZT]** Ma a hét utolsó munkanapja! Ne felejtsd el rendelni a jövő heti teletált! 🍕🥗"

        try:
            await channel.send(message)
            await interaction.response.send_message("✅ Teszt üzenet elküldve!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"baj van: {e}", ephemeral=True)

    # --- THE BACKGROUND LOOP ---

    @tasks.loop(minutes=60)
    async def teletal_loop(self):
        now = datetime.now()

        # 1. Find who needs a ping THIS hour
        active_guilds = {}
        for g_id, cfg in self.config.items():
            start_hour = cfg["hour"]
            amount = cfg.get("amount", 1)
            trigger_hours = [(start_hour + i) % 24 for i in range(amount)]

            if now.hour in trigger_hours:
                active_guilds[g_id] = cfg

        if not active_guilds:
            return # Nobody needs me, back to sleep! 💤

        # 2. Is today the day?
        last_workday = await get_last_workday()
        if not last_workday or now.date() != last_workday:
            return # Not the right day, back to sleep! 💤

        # 3. FIRE THE PINGS! 🍔💥
        for guild_id, cfg in active_guilds.items():
            channel = self.bot.get_channel(cfg["channel_id"])
            if channel:
                role_mention = f"<@&{cfg['role_id']}>"
                message = f"🍔🍟 {role_mention} Ma a hét utolsó munkanapja! Ne felejtsd el rendelni a jövő heti teletált! 🍕🥗"

                try:
                    await channel.send(message)
                    print(f"🍔 Üzenet elküldve: {channel.name} ({now.hour}:00)")
                except Exception as e:
                    print(f"baj van: {e}")

    @teletal_loop.before_loop
    async def before_teletal_loop(self):
        await self.bot.wait_until_ready()
        # Align perfectly to the top of the hour!
        now = datetime.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        wait_seconds = (next_hour - now).total_seconds() + 1
        print(f"🍔 Teletál loop vár {wait_seconds:.0f} másodpercet {next_hour.strftime('%H:%M')}-ig...")
        await asyncio.sleep(wait_seconds)

async def setup(bot):
    await bot.add_cog(teletalReminder(bot))
