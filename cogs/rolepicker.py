import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


DATA_FILE = Path("usr/rolepicker_roles.json")


class RolePicker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.roles = self.load_roles()

    def load_roles(self) -> dict[str, list[int]]:
        if DATA_FILE.exists():
            with DATA_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_roles(self):
        with DATA_FILE.open("w", encoding="utf-8") as f:
            json.dump(self.roles, f, indent=2)

    def get_guild_role_ids(self, guild_id: int) -> list[int]:
        return self.roles.get(str(guild_id), [])

    def add_guild_role(self, guild_id: int, role_id: int):
        guild_id = str(guild_id)
        self.roles.setdefault(guild_id, [])

        if role_id not in self.roles[guild_id]:
            self.roles[guild_id].append(role_id)
            self.save_roles()

    def remove_guild_role(self, guild_id: int, role_id: int):
        guild_id = str(guild_id)

        if guild_id in self.roles and role_id in self.roles[guild_id]:
            self.roles[guild_id].remove(role_id)
            self.save_roles()

    async def available_role_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if not interaction.guild:
            return []

        role_ids = self.get_guild_role_ids(interaction.guild.id)
        choices = []

        for role_id in role_ids:
            role = interaction.guild.get_role(role_id)

            if not role:
                continue

            if current.lower() not in role.name.lower():
                continue

            choices.append(app_commands.Choice(name=role.name, value=str(role.id)))

        return choices[:25]

    async def owned_role_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return []

        allowed_role_ids = set(self.get_guild_role_ids(interaction.guild.id))
        choices = []

        for role in interaction.user.roles:
            if role.id not in allowed_role_ids:
                continue

            if current.lower() not in role.name.lower():
                continue

            choices.append(app_commands.Choice(name=role.name, value=str(role.id)))

        return choices[:25]

    @app_commands.command(
        name="rolepicker_add",
        description="Admin: add a role to the self-serve role picker.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def rolepicker_add(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        if not interaction.guild:
            return

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "I can't manage that role because it is above or equal to my highest role.",
                ephemeral=True,
            )
            return

        self.add_guild_role(interaction.guild.id, role.id)

        await interaction.response.send_message(
            f"{role.mention} can now be self-assigned.",
            ephemeral=True,
        )

    @app_commands.command(
        name="rolepicker_remove",
        description="Admin: remove a role from the self-serve role picker.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def rolepicker_remove(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        if not interaction.guild:
            return

        self.remove_guild_role(interaction.guild.id, role.id)

        await interaction.response.send_message(
            f"{role.mention} was removed from the self-serve role picker.",
            ephemeral=True,
        )

    @app_commands.command(
        name="rolepicker_list",
        description="List self-serve roles available on this server.",
    )
    async def rolepicker_list(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        role_ids = self.get_guild_role_ids(interaction.guild.id)
        roles = [
            interaction.guild.get_role(role_id)
            for role_id in role_ids
            if interaction.guild.get_role(role_id)
        ]

        if not roles:
            await interaction.response.send_message(
                "No self-serve roles have been added yet.",
                ephemeral=True,
            )
            return

        role_list = "\n".join(role.mention for role in roles)

        await interaction.response.send_message(
            f"Self-serve roles:\n{role_list}",
            ephemeral=True,
        )

    @app_commands.command(
        name="iam",
        description="Add a self-serve role to yourself.",
    )
    @app_commands.autocomplete(role=available_role_autocomplete)
    async def iam(
        self,
        interaction: discord.Interaction,
        role: str,
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        picked_role = interaction.guild.get_role(int(role))

        if not picked_role:
            await interaction.response.send_message(
                "That role no longer exists.",
                ephemeral=True,
            )
            return

        if picked_role.id not in self.get_guild_role_ids(interaction.guild.id):
            await interaction.response.send_message(
                "That role is not self-assignable.",
                ephemeral=True,
            )
            return

        if picked_role in interaction.user.roles:
            await interaction.response.send_message(
                f"You already have {picked_role.mention}.",
                ephemeral=True,
            )
            return

        await interaction.user.add_roles(
            picked_role,
            reason="Self-serve role picker",
        )

        await interaction.response.send_message(
            f"Added {picked_role.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="iamnot",
        description="Remove one of your self-serve roles.",
    )
    @app_commands.autocomplete(role=owned_role_autocomplete)
    async def iamnot(
        self,
        interaction: discord.Interaction,
        role: str,
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        picked_role = interaction.guild.get_role(int(role))

        if not picked_role:
            await interaction.response.send_message(
                "That role no longer exists.",
                ephemeral=True,
            )
            return

        if picked_role not in interaction.user.roles:
            await interaction.response.send_message(
                "You don't have that role.",
                ephemeral=True,
            )
            return

        await interaction.user.remove_roles(
            picked_role,
            reason="Self-serve role picker",
        )

        await interaction.response.send_message(
            f"Removed {picked_role.mention}.",
            ephemeral=True,
        )

    @rolepicker_add.error
    @rolepicker_remove.error
    async def admin_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Only admins can use this command.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(RolePicker(bot))