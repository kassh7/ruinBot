import discord
from discord.ext import commands, tasks
import asyncio
import json
import os
from datetime import datetime, timedelta, time
from cogs.holiday_cache import get_last_workday

CONFIG_FILE = "usr/teletal_config.json"

ROLE_PING = discord.AllowedMentions(roles=True)


class teletalReminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = self.load_config()
        self._loop_task = None

    def cog_unload(self):
        if self._loop_task:
            self._loop_task.cancel()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        return {}

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=4)

    def reschedule(self):
        """Cancel the current sleep loop and restart it so new config is picked up immediately."""
        if self._loop_task:
            self._loop_task.cancel()
        self._loop_task = asyncio.ensure_future(self._run_loop())

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
        self.reschedule()

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
            self.reschedule()
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
            await channel.send(message, allowed_mentions=ROLE_PING)
            await interaction.response.send_message("✅ Teszt üzenet elküldve!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"baj van: {e}", ephemeral=True)


    async def _run_loop(self):
        await self.bot.wait_until_ready()

        while True:
            try:
                sleep_seconds = await self._get_seconds_until_next_trigger()

                if sleep_seconds is None:
                    # No guilds configured, check again tomorrow
                    print("🍔 Teletál: nincs konfiguráció, holnap újrapróbálom...")
                    await asyncio.sleep(86400)
                    continue

                next_wake = datetime.now() + timedelta(seconds=sleep_seconds)
                print(f"🍔 Teletál loop alszik {sleep_seconds:.0f} másodpercet, ébredés: {next_wake.strftime('%Y-%m-%d %H:%M')}")
                await asyncio.sleep(sleep_seconds)

                await self._fire_reminders()

            except asyncio.CancelledError:
                print("🍔 Teletál loop leállítva (reschedule vagy shutdown).")
                return
            except Exception as e:
                print(f"baj van a teletál loopban: {e}")
                await asyncio.sleep(60)  # Brief pause before retrying on unexpected errors

    async def _get_seconds_until_next_trigger(self):
        """Calculate seconds until the next trigger datetime across all configured guilds."""
        if not self.config:
            return None

        last_workday = await get_last_workday()
        now = datetime.now()

        trigger_datetimes = []
        for cfg in self.config.values():
            for i in range(cfg.get("amount", 1)):
                trigger_hour = (cfg["hour"] + i) % 24
                trigger_dt = datetime.combine(last_workday, time(hour=trigger_hour, minute=0, second=0))
                if trigger_dt > now:
                    trigger_datetimes.append(trigger_dt)

        if not trigger_datetimes:
            # All triggers for this week have passed — sleep until next Monday and recalculate
            days_until_monday = (7 - now.weekday()) % 7 or 7
            monday_midnight = datetime.combine(
                now.date() + timedelta(days=days_until_monday),
                time(hour=0, minute=1)
            )
            return (monday_midnight - now).total_seconds()

        next_trigger = min(trigger_datetimes)
        return (next_trigger - now).total_seconds()

    async def _fire_reminders(self):
        """Send reminders to all guilds whose trigger time matches right now."""
        last_workday = await get_last_workday()
        now = datetime.now()

        if now.date() != last_workday:
            return  # Woke up on the right time but wrong day (shouldn't happen, but be safe)

        for guild_id, cfg in self.config.items():
            trigger_hours = [(cfg["hour"] + i) % 24 for i in range(cfg.get("amount", 1))]
            if now.hour not in trigger_hours:
                continue

            channel = self.bot.get_channel(cfg["channel_id"])
            if not channel:
                print(f"baj van: nem találom a csatornát a guild {guild_id}-ban")
                continue

            role_mention = f"<@&{cfg['role_id']}>"
            message = f"🍔🍟 {role_mention} Ma a hét utolsó munkanapja! Ne felejtsd el rendelni a jövő heti teletált! 🍕🥗"

            try:
                await channel.send(message, allowed_mentions=ROLE_PING)
                print(f"🍔 Üzenet elküldve: {channel.name} ({now.hour}:00)")
            except Exception as e:
                print(f"baj van: {e}")


async def setup(bot):
    cog = teletalReminder(bot)
    await bot.add_cog(cog)
    # Start the loop after the cog is registered
    cog._loop_task = asyncio.ensure_future(cog._run_loop())