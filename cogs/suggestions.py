import os
import json
import discord
from discord import app_commands, ui, Interaction
from discord.ext import commands

SETTINGS_FILE = "settings.json"


def load_settings() -> dict:
    defaults = {"suggestions_channel_id": None}
    if not os.path.exists(SETTINGS_FILE):
        return defaults
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return defaults


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
        settings = load_settings()
        ch_id = settings.get("suggestions_channel_id")

        # Try to get channel by ID first, then fallback to name auto-detect
        suggestions_channel = None
        if ch_id:
            suggestions_channel = guild.get_channel(ch_id)
        if suggestions_channel is None:
            for ch in guild.text_channels:
                if "suggestions" in ch.name.lower() or "sugerencias" in ch.name.lower():
                    suggestions_channel = ch
                    break

        if suggestions_channel is None:
            await interaction.response.send_message(
                "❌ No se encontró el canal de sugerencias. Pídele al admin que lo configure con `/settings suggestions_channel`.",
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
