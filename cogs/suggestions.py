import os
import discord
from discord import app_commands, ui, Interaction
from discord.ext import commands

# Auto-detect channel with this name (case-insensitive)
SUGGESTIONS_CHANNEL_NAME = "suggestions"


# ---------------------
# Modal
# ---------------------
class SuggestionModal(ui.Modal, title="💡 Nueva Sugerencia"):
    suggestion_title = ui.TextInput(
        label="Título de tu sugerencia",
        placeholder="Ej: Añade un comando de música...",
        required=True,
        max_length=100
    )
    suggestion_body = ui.TextInput(
        label="Descripción (opcional)",
        placeholder="Explica tu idea con más detalle...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: Interaction):
        guild = interaction.guild

        # Find the suggestions channel
        suggestions_channel = None
        for ch in guild.text_channels:
            if SUGGESTIONS_CHANNEL_NAME in ch.name.lower():
                suggestions_channel = ch
                break

        if suggestions_channel is None:
            await interaction.response.send_message(
                f"❌ No se encontró un canal llamado `{SUGGESTIONS_CHANNEL_NAME}`. Pídele al admin que lo cree.",
                ephemeral=True
            )
            return

        # Build the embed
        embed = discord.Embed(
            title=f"💡 {self.suggestion_title.value}",
            description=self.suggestion_body.value or "*Sin descripción adicional.*",
            color=discord.Color.gold()
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url
        )
        embed.set_footer(text=f"Sugerencia de {interaction.user} • ID: {interaction.user.id}")

        # Post it to the suggestions channel with voting reactions
        msg = await suggestions_channel.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        await interaction.response.send_message(
            "✅ ¡Tu sugerencia ha sido enviada! Los mods la revisarán pronto.",
            ephemeral=True
        )

    async def on_error(self, interaction: Interaction, error: Exception):
        await interaction.response.send_message(
            f"⚠️ Error al enviar la sugerencia: {error}", ephemeral=True
        )


# ---------------------
# Cog
# ---------------------
class Suggestions(commands.Cog, name="Suggestions"):
    """Sistema de sugerencias con modal de Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="suggest", description="Envía una sugerencia para el bot o el servidor.")
    async def suggest(self, interaction: Interaction):
        modal = SuggestionModal(self.bot)
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot):
    await bot.add_cog(Suggestions(bot))
