import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# The two Vocard bot user IDs, loaded from .env
VOCARD_IDS = set(int(i) for i in os.getenv("VOCARD_IDS", "").split(",") if i.strip())

# Vocard's command prefixes
VOCARD_PREFIXES = ("!", "?")

# How long (in seconds) before messages are deleted
DELETE_AFTER = 30

# How long (in seconds) to wait for a Vocard reply before giving up on a user command
REPLY_WINDOW = 5


async def _delete_after(message: discord.Message, delay: float) -> None:
    """Wait `delay` seconds then delete `message`, ignoring errors if it's already gone."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except discord.NotFound:
        pass  # already deleted, no problem
    except discord.Forbidden:
        logger.warning(
            "Missing permissions to delete message %s in channel %s",
            message.id,
            message.channel,
        )
    except discord.HTTPException as e:
        logger.error("Failed to delete message %s: %s", message.id, e)


class VocardCleanup(commands.Cog):
    """
    Automatically deletes messages related to the two Vocard music bot instances
    after a configurable delay (default: 30 seconds).

    Covers:
      - Any message *sent by* either Vocard bot
      - Any message *sent by a user* that starts with a Vocard prefix (! or ?)
        BUT ONLY if Vocard actually replies in the same channel within REPLY_WINDOW seconds,
        confirming it was a Vocard command and not another bot's command
      - Edited Vocard messages (e.g. "Now Playing" embed updates)
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Tracks message IDs that already have a pending deletion task
        self._pending: set[int] = set()
        # Pending user commands waiting to see if Vocard replies:
        # { channel_id: [ (message, asyncio.TimerHandle) ] }
        self._waiting_commands: dict[int, list[tuple[discord.Message, asyncio.TimerHandle]]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _schedule(self, message: discord.Message) -> None:
        """Schedule a message for deletion if not already scheduled."""
        if message.id in self._pending:
            return
        self._pending.add(message.id)
        task = asyncio.create_task(_delete_after(message, DELETE_AFTER))
        task.add_done_callback(lambda _: self._pending.discard(message.id))

    def _is_vocard_message(self, message: discord.Message) -> bool:
        return message.author.id in VOCARD_IDS

    def _is_prefixed_user_message(self, message: discord.Message) -> bool:
        """A human-sent, guild channel message starting with a Vocard prefix."""
        if message.author.bot:
            return False
        if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return False
        return message.content.startswith(VOCARD_PREFIXES)

    def _confirm_waiting_commands(self, channel_id: int) -> None:
        """
        Vocard just spoke in this channel — schedule all user commands that were
        waiting for confirmation, and clear the waiting list.
        """
        for msg, handle in self._waiting_commands.pop(channel_id, []):
            handle.cancel()
            self._schedule(msg)

    def _expire_waiting_command(self, channel_id: int, message: discord.Message) -> None:
        """
        Called when the reply window expires with no Vocard reply.
        Removes the specific message from the waiting list (it was not a Vocard command).
        """
        waiting = self._waiting_commands.get(channel_id, [])
        self._waiting_commands[channel_id] = [
            (m, h) for m, h in waiting if m.id != message.id
        ]
        if not self._waiting_commands[channel_id]:
            self._waiting_commands.pop(channel_id, None)

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Vocard bot sent a message — schedule it for deletion and confirm any
        # waiting user commands in this channel
        if self._is_vocard_message(message):
            self._schedule(message)
            self._confirm_waiting_commands(message.channel.id)
            return

        # User sent a prefixed message — hold it and wait to see if Vocard replies
        if self._is_prefixed_user_message(message):
            loop = asyncio.get_event_loop()
            handle = loop.call_later(
                REPLY_WINDOW,
                self._expire_waiting_command,
                message.channel.id,
                message,
            )
            self._waiting_commands.setdefault(message.channel.id, []).append((message, handle))

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Catch Vocard editing its own messages (e.g. Now Playing embed updates)."""
        if self._is_vocard_message(after):
            self._schedule(after)

    # ------------------------------------------------------------------
    # Owner-only management commands  (prefix: r!)
    # ------------------------------------------------------------------

    @commands.group(name="vocardclean", invoke_without_command=True)
    @commands.is_owner()
    async def vocardclean(self, ctx: commands.Context) -> None:
        """Manage the Vocard auto-delete feature."""
        waiting_total = sum(len(v) for v in self._waiting_commands.values())
        await ctx.send(
            f"**VocardCleanup** is active.\n"
            f"Watching user IDs: `{', '.join(str(i) for i in VOCARD_IDS)}`\n"
            f"Vocard prefixes: `{'`, `'.join(VOCARD_PREFIXES)}`\n"
            f"Delete delay: `{DELETE_AFTER}s` — Reply window: `{REPLY_WINDOW}s`\n"
            f"Pending deletions: `{len(self._pending)}` — Awaiting Vocard reply: `{waiting_total}`"
        )

    @vocardclean.command(name="test")
    @commands.is_owner()
    async def vocardclean_test(self, ctx: commands.Context) -> None:
        """Send a test message that self-deletes after the configured delay."""
        msg = await ctx.send(
            f"✅ VocardCleanup test — this message will be deleted in {DELETE_AFTER}s."
        )
        self._schedule(msg)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VocardCleanup(bot))