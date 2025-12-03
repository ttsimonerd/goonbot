import os
import discord
from discord import app_commands, Interaction, ui
from discord.ext import commands
from probabilities import roll_with_limit

PASSWORD = os.getenv("SECRET_CMD_PASSWORD")
ALLOWED_USER_ID = YOUR_USER_ID  # Reemplaza este valor con tu ID


# ---------------------------------------------
#   MODAL DE CONTRASEÑA
# ---------------------------------------------
class PasswordModal(ui.Modal, title="Autenticación requerida"):
    password = ui.TextInput(
        label="Introduce la contraseña",
        placeholder="Escribe aquí...",
        required=True,
        min_length=1
    )

    async def on_submit(self, interaction: Interaction):
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
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="secreto",
        description="Comando reservado únicamente para el administrador autorizado."
    )
    async def secret(self, interaction: Interaction):

        # Solo tú puedes usarlo
        if interaction.user.id != ALLOWED_USER_ID:
            await interaction.response.send_message(
                "No tienes permiso para usar este comando.",
                ephemeral=True
            )
            return

        # Abrir modal de contraseña
        modal = PasswordModal()
        await interaction.response.send_modal(modal)


async def setup(bot):
    await bot.add_cog(SecretCommand(bot))