import discord
from discord import app_commands, Interaction
from discord.ext import commands

import db


class Settings(commands.Cog, name="Settings"):
    """Configuración del bot para admins."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    settings_group = app_commands.Group(
        name="settings",
        description="⚙️ Configura el bot. Solo admins.",
        default_permissions=discord.Permissions(administrator=True)
    )

    @settings_group.command(name="view", description="Muestra la configuración actual del bot.")
    async def view(self, interaction: Interaction):
        data = await db.get_settings(interaction.guild_id)

        gambling_ch = interaction.guild.get_channel(data["gambling_channel_id"]) if data["gambling_channel_id"] else None
        suggestions_ch = interaction.guild.get_channel(data["suggestions_channel_id"]) if data["suggestions_channel_id"] else None
        winning_ch = interaction.guild.get_channel(data["gambling_winners_channel_id"]) if data["gambling_winners_channel_id"] else None

        embed = discord.Embed(title="⚙️ Configuración actual de Goonbot", color=discord.Color.blurple())
        embed.add_field(
            name="🎲 Canal de Gambling",
            value=gambling_ch.mention if gambling_ch else "*(auto-detect por nombre)*",
            inline=False
        )
        embed.add_field(
            name="🏆 Canal de Ganadores Diarios",
            value=winning_ch.mention if winning_ch else "*(auto-detect por nombre)*",
            inline=False
        )
        embed.add_field(name="⏱️ Duración del ban de gambling", value=f"{data['gambling_lockout_hours']} horas", inline=True)
        embed.add_field(name="⚠️ Warns para banear", value=str(data["gambling_max_warns"]), inline=True)
        embed.add_field(
            name="💡 Canal de Sugerencias",
            value=suggestions_ch.mention if suggestions_ch else "*(auto-detect por nombre)*",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="gambling_channel", description="Establece el canal de gambling.")
    @app_commands.describe(channel="Canal donde se juega al gambling")
    async def set_gambling_channel(self, interaction: Interaction, channel: discord.TextChannel):
        await db.update_settings(interaction.guild_id, gambling_channel_id=str(channel.id))
        await interaction.response.send_message(f"✅ Canal de gambling establecido en {channel.mention}.", ephemeral=True)

    @settings_group.command(name="suggestions_channel", description="Establece el canal de sugerencias.")
    @app_commands.describe(channel="Canal donde se envían las sugerencias")
    async def set_suggestions_channel(self, interaction: Interaction, channel: discord.TextChannel):
        await db.update_settings(interaction.guild_id, suggestions_channel_id=str(channel.id))
        await interaction.response.send_message(f"✅ Canal de sugerencias establecido en {channel.mention}.", ephemeral=True)

    @settings_group.command(name="winners_channel", description="Establece el canal para los ganadores diarios de gambling.")
    @app_commands.describe(channel="Canal donde se publica el ranking diario")
    async def set_winners_channel(self, interaction: Interaction, channel: discord.TextChannel):
        await db.update_settings(interaction.guild_id, gambling_winners_channel_id=str(channel.id))
        await interaction.response.send_message(f"✅ Canal de ganadores diarios establecido en {channel.mention}.", ephemeral=True)

    @settings_group.command(name="lockout_hours", description="Establece las horas de ban por gambling.")
    @app_commands.describe(hours="Número de horas del ban (mínimo 1)")
    async def set_lockout_hours(self, interaction: Interaction, hours: int):
        if hours < 1:
            await interaction.response.send_message("❌ El mínimo es 1 hora.", ephemeral=True)
            return
        await db.update_settings(interaction.guild_id, gambling_lockout_hours=hours)
        await interaction.response.send_message(f"✅ Ban de gambling actualizado a **{hours} horas**.", ephemeral=True)

    @settings_group.command(name="max_warns", description="Establece los warns máximos antes del ban de gambling.")
    @app_commands.describe(warns="Número de warns (mínimo 1)")
    async def set_max_warns(self, interaction: Interaction, warns: int):
        if warns < 1:
            await interaction.response.send_message("❌ El mínimo es 1 warn.", ephemeral=True)
            return
        await db.update_settings(interaction.guild_id, gambling_max_warns=warns)
        await interaction.response.send_message(f"✅ Warns máximos actualizados a **{warns}**.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
