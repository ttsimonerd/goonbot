import os
import json
import discord
from discord import app_commands, Interaction, ui
from discord.ext import commands

SETTINGS_FILE = "settings.json"

# Defaults
DEFAULT_SETTINGS = {
    "gambling_channel_id": None,
    "gambling_lockout_hours": 24,
    "gambling_max_warns": 3,
    "suggestions_channel_id": None,
}


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS.copy()
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            # Fill in missing keys with defaults
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            return data
        except json.JSONDecodeError:
            return DEFAULT_SETTINGS.copy()


def save_settings(data: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# -----------------------------------------------
# Settings Cog
# -----------------------------------------------
class Settings(commands.Cog, name="Settings"):
    """Configuración del bot para admins."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    settings_group = app_commands.Group(
        name="settings",
        description="⚙️ Configura el bot. Solo admins.",
        default_permissions=discord.Permissions(administrator=True)
    )

    # --- View current settings ---
    @settings_group.command(name="view", description="Muestra la configuración actual del bot.")
    async def view(self, interaction: Interaction):
        data = load_settings()

        gambling_ch = interaction.guild.get_channel(data["gambling_channel_id"]) if data["gambling_channel_id"] else None
        suggestions_ch = interaction.guild.get_channel(data["suggestions_channel_id"]) if data["suggestions_channel_id"] else None

        embed = discord.Embed(
            title="⚙️ Configuración actual de Goonbot",
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="🎲 Canal de Gambling",
            value=gambling_ch.mention if gambling_ch else "*(auto-detect por nombre)*",
            inline=False
        )
        embed.add_field(
            name="⏱️ Duración del ban de gambling",
            value=f"{data['gambling_lockout_hours']} horas",
            inline=True
        )
        embed.add_field(
            name="⚠️ Warns para banear",
            value=str(data["gambling_max_warns"]),
            inline=True
        )
        embed.add_field(
            name="💡 Canal de Sugerencias",
            value=suggestions_ch.mention if suggestions_ch else "*(auto-detect por nombre)*",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- Set gambling channel ---
    @settings_group.command(name="gambling_channel", description="Establece el canal de gambling.")
    @app_commands.describe(channel="Canal donde se juega al gambling")
    async def set_gambling_channel(self, interaction: Interaction, channel: discord.TextChannel):
        data = load_settings()
        data["gambling_channel_id"] = channel.id
        save_settings(data)
        await interaction.response.send_message(
            f"✅ Canal de gambling establecido en {channel.mention}.", ephemeral=True
        )

    # --- Set suggestions channel ---
    @settings_group.command(name="suggestions_channel", description="Establece el canal de sugerencias.")
    @app_commands.describe(channel="Canal donde se envían las sugerencias")
    async def set_suggestions_channel(self, interaction: Interaction, channel: discord.TextChannel):
        data = load_settings()
        data["suggestions_channel_id"] = channel.id
        save_settings(data)
        await interaction.response.send_message(
            f"✅ Canal de sugerencias establecido en {channel.mention}.", ephemeral=True
        )

    # --- Set gambling lockout hours ---
    @settings_group.command(name="lockout_hours", description="Establece las horas de ban por gambling.")
    @app_commands.describe(hours="Número de horas del ban (mínimo 1)")
    async def set_lockout_hours(self, interaction: Interaction, hours: int):
        if hours < 1:
            await interaction.response.send_message("❌ El mínimo es 1 hora.", ephemeral=True)
            return
        data = load_settings()
        data["gambling_lockout_hours"] = hours
        save_settings(data)
        await interaction.response.send_message(
            f"✅ Ban de gambling actualizado a **{hours} horas**.", ephemeral=True
        )

    # --- Set max warns ---
    @settings_group.command(name="max_warns", description="Establece los warns máximos antes del ban de gambling.")
    @app_commands.describe(warns="Número de warns (mínimo 1)")
    async def set_max_warns(self, interaction: Interaction, warns: int):
        if warns < 1:
            await interaction.response.send_message("❌ El mínimo es 1 warn.", ephemeral=True)
            return
        data = load_settings()
        data["gambling_max_warns"] = warns
        save_settings(data)
        await interaction.response.send_message(
            f"✅ Warns máximos actualizados a **{warns}**.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
