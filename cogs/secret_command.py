import discord
from discord import app_commands, Interaction, ui
from discord.ext import commands
from probabilities import roll_with_limit
from config import ADMIN_USER_ID as ALLOWED_USER_ID, SECRET_CMD_PASSWORD as PASSWORD


# ---------------------------------------------
#   MODAL DE CONTRASEÑA
# ---------------------------------------------
class PasswordModal(ui.Modal, title="Autenticación requerida"):
    """Modal que pide la contraseña antes de ejecutar el comando secreto."""

    password = ui.TextInput(
        label="Introduce la contraseña",
        placeholder="Escribe aquí...",
        required=True,
        min_length=1
    )

    async def on_submit(self, interaction: Interaction) -> None:
        """Comprueba la contraseña y muestra el resultado del roll."""
        if not PASSWORD:
            await interaction.response.send_message(
                "❌ SECRET_CMD_PASSWORD no está configurada en el servidor.",
                ephemeral=True
            )
            return

        user_input = str(self.password.value).strip()

        if user_input != PASSWORD:
            await interaction.response.send_message(
                "Contraseña incorrecta.",
                ephemeral=True
            )
            return

        result = roll_with_limit()

        await interaction.response.send_message(
            f"Resultado: {result}",
            ephemeral=True
        )


# ---------------------------------------------
#   COG PRINCIPAL
# ---------------------------------------------
class SecretCommand(commands.Cog):
    """Comando secreto protegido por contraseña y restringido al admin."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="admindashboard",
        description="Comando reservado únicamente para el administrador autorizado."
    )
    async def secret(self, interaction: Interaction) -> None:
        """Abre el modal de contraseña (solo admin autorizado)."""
        # Solo tú puedes usarlo
        if interaction.user.id != ALLOWED_USER_ID:
            await interaction.response.send_message(
                "No tienes permiso para usar este comando.",
                ephemeral=True
            )
            return

        if not PASSWORD:
            await interaction.response.send_message(
                "❌ SECRET_CMD_PASSWORD no está configurada en el servidor.",
                ephemeral=True
            )
            return

        # Abrir modal de contraseña
        modal = PasswordModal()
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SecretCommand(bot))