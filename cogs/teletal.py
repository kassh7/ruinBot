import asyncio
import json
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import commands

from utils.holiday_cache import get_last_workday

try:
    BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
except ZoneInfoNotFoundError:
    raise RuntimeError(
        "Missing timezone data for Europe/Budapest. "
    )

CONFIG_FILE = "usr/teletal_config.json"
ROLE_PING = discord.AllowedMentions(roles=True)

DAY_NAMES_HU = [
    "hétfő",
    "kedd",
    "szerda",
    "csütörtök",
    "péntek",
    "szombat",
    "vasárnap",
]


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
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_config(self):
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

    def reschedule(self):
        if self._loop_task:
            self._loop_task.cancel()
        self._loop_task = asyncio.create_task(self._run_loop())

    def _build_trigger_datetimes_for_day(self, day_date, start_hour, amount):
        trigger_datetimes = []
        for i in range(amount):
            trigger_hour = (start_hour + i) % 24
            trigger_dt = datetime.combine(
                day_date,
                time(hour=trigger_hour, minute=0, second=0),
                tzinfo=BUDAPEST_TZ
            )
            trigger_datetimes.append(trigger_dt)
        return trigger_datetimes

    async def _get_next_trigger_for_guild(self, cfg):
        """
        Returns the next actual trigger datetime for one guild.
        Searches forward week by week until it finds a future trigger.
        """
        now = datetime.now(BUDAPEST_TZ)

        for week_offset in range(0, 16):
            base_date = now.date() + timedelta(days=7 * week_offset)
            target_day = await get_last_workday(base_date)

            trigger_datetimes = self._build_trigger_datetimes_for_day(
                target_day,
                cfg["hour"],
                cfg.get("amount", 1)
            )

            future_triggers = [dt for dt in trigger_datetimes if dt > now]
            if future_triggers:
                return min(future_triggers)

        return None

    async def _get_next_trigger_across_all_guilds(self):
        if not self.config:
            return None

        candidates = []
        for cfg in self.config.values():
            next_trigger = await self._get_next_trigger_for_guild(cfg)
            if next_trigger is not None:
                candidates.append(next_trigger)

        return min(candidates) if candidates else None

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
    async def setup_teletal(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role,
        hour: int,
        amount: int = 1
    ):
        if hour < 0 or hour > 23:
            await interaction.response.send_message(
                "❌ Legyen már 0-23 közt az óra plz...",
                ephemeral=True
            )
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
            f"✅ Teletál reminder beállítva! Pingelem: {role.mention}, ide: {channel.mention}, "
            f"{time_str}, minden hét utolsó munkanapján.",
            ephemeral=True
        )

    @teletal.command(name="disable", description="Kikapcsolja a teletál remindert a szerveren.")
    async def disable_teletal(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)

        if guild_id in self.config:
            del self.config[guild_id]
            self.save_config()
            self.reschedule()
            await interaction.response.send_message(
                "🛑 Teletál reminder kikapcsolva.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "⚠️ Eddig sem volt reminder helo!",
                ephemeral=True
            )

    @teletal.command(name="test", description="Teszt üzenet küldése, hogy lássuk működik-e.")
    async def test_teletal(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)

        if guild_id not in self.config:
            await interaction.response.send_message(
                "❌ Előbb futtasd a `/teletal setup`-ot!",
                ephemeral=True
            )
            return

        cfg = self.config[guild_id]
        channel = self.bot.get_channel(cfg["channel_id"])

        if not channel:
            await interaction.response.send_message(
                "baj van: nem találom a csatornát!",
                ephemeral=True
            )
            return

        role_mention = f"<@&{cfg['role_id']}>"
        message = (
            f"🍔🍟 {role_mention} **[TESZT]** Ma a hét utolsó munkanapja! "
            f"Ne felejtsd el rendelni a jövő heti teletált! 🍕🥗"
        )

        try:
            await channel.send(message, allowed_mentions=ROLE_PING)
            await interaction.response.send_message(
                "✅ Teszt üzenet elküldve!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"baj van: {e}",
                ephemeral=True
            )

    @teletal.command(name="status", description="Megmutatja mikor fog legközelebb menni a teletál reminder.")
    async def status_teletal(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)

        if guild_id not in self.config:
            await interaction.response.send_message(
                "❌ Erre a szerverre nincs beállítva teletál reminder.",
                ephemeral=True
            )
            return

        cfg = self.config[guild_id]
        now = datetime.now(BUDAPEST_TZ)

        this_week_last_workday = await get_last_workday(now.date())
        this_week_triggers = self._build_trigger_datetimes_for_day(
            this_week_last_workday,
            cfg["hour"],
            cfg.get("amount", 1)
        )
        future_this_week = [dt for dt in this_week_triggers if dt > now]
        next_trigger = await self._get_next_trigger_for_guild(cfg)

        hour_list = [
            f"{(cfg['hour'] + i) % 24:02d}:00"
            for i in range(cfg.get("amount", 1))
        ]

        desc_lines = [
            f"**Csatorna:** <#{cfg['channel_id']}>",
            f"**Pingelt role:** <@&{cfg['role_id']}>",
            f"**Beállított órák:** {', '.join(hour_list)}",
            f"**E heti utolsó munkanap:** {this_week_last_workday.strftime('%Y-%m-%d')} ({DAY_NAMES_HU[this_week_last_workday.weekday()]})",
        ]

        if future_this_week:
            desc_lines.append(
                f"**Még hátralévő eheti időpontok:** {', '.join(dt.strftime('%H:%M') for dt in future_this_week)}"
            )
        else:
            desc_lines.append("**Még hátralévő eheti időpontok:** nincs")

        if next_trigger:
            desc_lines.append(
                f"**Következő tényleges reminder:** {next_trigger.strftime('%Y-%m-%d %H:%M %Z')} "
                f"({DAY_NAMES_HU[next_trigger.weekday()]})"
            )
            delta = next_trigger - now
            total_seconds = int(delta.total_seconds())
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            desc_lines.append(
                f"**Ennyi múlva:** {days} nap, {hours} óra, {minutes} perc"
            )
        else:
            desc_lines.append("**Következő tényleges reminder:** nem található")

        embed = discord.Embed(
            title="🍔 Teletál reminder állapot",
            description="\n".join(desc_lines),
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"Most: {now.strftime('%Y-%m-%d %H:%M %Z')}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _run_loop(self):
        await self.bot.wait_until_ready()

        while True:
            try:
                next_trigger = await self._get_next_trigger_across_all_guilds()

                if next_trigger is None:
                    print("🍔 Teletál: nincs konfiguráció, holnap újrapróbálom...")
                    await asyncio.sleep(86400)
                    continue

                now = datetime.now(BUDAPEST_TZ)
                sleep_seconds = max(0, (next_trigger - now).total_seconds())

                print(
                    f"🍔 Teletál loop alszik {sleep_seconds:.0f} másodpercet, "
                    f"ébredés: {next_trigger.strftime('%Y-%m-%d %H:%M %Z')}"
                )

                await asyncio.sleep(sleep_seconds)
                await self._fire_reminders()

            except asyncio.CancelledError:
                print("🍔 Teletál loop leállítva (reschedule vagy shutdown).")
                return
            except Exception as e:
                print(f"baj van a teletál loopban: {e}")
                await asyncio.sleep(60)

    async def _fire_reminders(self):
        """
        Fires based on the actual current Budapest date/hour.
        This avoids edge cases from recalculating the next trigger at wake time.
        """
        now = datetime.now(BUDAPEST_TZ)
        today = now.date()

        if now.minute != 0:
            return

        for guild_id, cfg in self.config.items():
            last_workday = await get_last_workday(today)

            if today != last_workday:
                continue

            trigger_hours = [
                (cfg["hour"] + i) % 24
                for i in range(cfg.get("amount", 1))
            ]

            if now.hour not in trigger_hours:
                continue

            channel = self.bot.get_channel(cfg["channel_id"])
            if not channel:
                print(f"baj van: nem találom a csatornát a guild {guild_id}-ban")
                continue

            role_mention = f"<@&{cfg['role_id']}>"
            message = (
                f"🍔🍟 {role_mention} Ma a hét utolsó munkanapja! "
                f"Ne felejtsd el rendelni a jövő heti teletált! 🍕🥗"
            )

            try:
                await channel.send(message, allowed_mentions=ROLE_PING)
                print(f"🍔 Üzenet elküldve: {channel.name} ({now.strftime('%H:%M %Z')})")
            except Exception as e:
                print(f"baj van: {e}")


async def setup(bot):
    cog = teletalReminder(bot)
    await bot.add_cog(cog)
    cog._loop_task = asyncio.create_task(cog._run_loop())