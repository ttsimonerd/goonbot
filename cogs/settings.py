import discord
from discord import app_commands, Interaction
from discord.ext import commands

import db


class Settings(commands.Cog, name="Settings"):
    """Comandos /settings para gestionar la configuración del bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    settings_group = app_commands.Group(
        name="settings",
        description="[ADMIN]",
        default_permissions=discord.Permissions(administrator=True)
    )

    @settings_group.command(name="view", description="Show current config")
    async def view(self, interaction: Interaction) -> None:
        """Muestra la configuración actual del bot."""
        if interaction.guild is None or interaction.guild_id is None:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return

        data = await db.get_settings(interaction.guild_id)

        gambling_ch = interaction.guild.get_channel(data["gambling_channel_id"]) if data["gambling_channel_id"] else None
        suggestions_ch = interaction.guild.get_channel(data["suggestions_channel_id"]) if data["suggestions_channel_id"] else None
        winning_ch = interaction.guild.get_channel(data["gambling_winners_channel_id"]) if data["gambling_winners_channel_id"] else None
        music_ch = interaction.guild.get_channel(data["music_channel_id"]) if data["music_channel_id"] else None
        music_battle_ch = interaction.guild.get_channel(data["music_battle_channel_id"]) if data["music_battle_channel_id"] else None

        embed = discord.Embed(title="⚙️ GoonBot's config", color=discord.Color.blurple())
        embed.add_field(
            name="🎲 Gambling config:",
            value=gambling_ch.mention if gambling_ch else "*(auto-detect por nombre)*",
            inline=False
        )
        embed.add_field(
            name="🏆 Daily wins config:",
            value=winning_ch.mention if winning_ch else "*(auto-detect por nombre)*",
            inline=False
        )
        embed.add_field(name="⏱️ Gambling ban config:", value=f"{data['gambling_lockout_hours']} horas", inline=True)
        embed.add_field(name="⚠️ Warns for ban config:", value=str(data["gambling_max_warns"]), inline=True)
        embed.add_field(
            name="💡 Suggestion channel config:",
            value=suggestions_ch.mention if suggestions_ch else "*(auto-detect por nombre)*",
            inline=False
        )
        embed.add_field(
            name="🎵 Music links channel:",
            value=music_ch.mention if music_ch else "*(not set)*",
            inline=False
        )
        embed.add_field(
            name="⚔️ Music battle channel:",
            value=music_battle_ch.mention if music_battle_ch else "*(not set)*",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="gambling_channel", description="Set gambling channel.")
    @app_commands.describe(channel="Gambling channel")
    async def set_gambling_channel(self, interaction: Interaction, channel: discord.TextChannel) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return
        await db.update_settings(interaction.guild_id, gambling_channel_id=str(channel.id))
        await interaction.response.send_message(f"✅ Channel set to: {channel.mention}.", ephemeral=True)

    @settings_group.command(name="suggestions_channel", description="Set suggestions channel.")
    @app_commands.describe(channel="Suggestions channel")
    async def set_suggestions_channel(self, interaction: Interaction, channel: discord.TextChannel) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return
        await db.update_settings(interaction.guild_id, suggestions_channel_id=str(channel.id))
        await interaction.response.send_message(f"✅ Channel set to: {channel.mention}.", ephemeral=True)

    @settings_group.command(name="winners_channel", description="Set daily wins channel.")
    @app_commands.describe(channel="Daily wins channel")
    async def set_winners_channel(self, interaction: Interaction, channel: discord.TextChannel) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return
        await db.update_settings(interaction.guild_id, gambling_winners_channel_id=str(channel.id))
        await interaction.response.send_message(f"✅ Channel set to: {channel.mention}.", ephemeral=True)

    @settings_group.command(name="lockout_hours", description="Set timeout gambling hours.")
    @app_commands.describe(hours="Minimum 1 hour")
    async def set_lockout_hours(self, interaction: Interaction, hours: int) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return
        if hours < 1:
            await interaction.response.send_message("❌ Minimum 1 hour nih", ephemeral=True)
            return
        await db.update_settings(interaction.guild_id, gambling_lockout_hours=hours)
        await interaction.response.send_message(f"✅ Gambling ban now lasts: **{hours} hours**.", ephemeral=True)

    @settings_group.command(name="max_warns", description="Set maximum warns before ban.")
    @app_commands.describe(warns="Minimum 1")
    async def set_max_warns(self, interaction: Interaction, warns: int) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return
        if warns < 1:
            await interaction.response.send_message("❌ Minimum 1 nih", ephemeral=True)
            return
        await db.update_settings(interaction.guild_id, gambling_max_warns=warns)
        await interaction.response.send_message(f"✅ Maximum warns before ban set to: **{warns} warns**.", ephemeral=True)

    @settings_group.command(name="music_channel", description="Set the channel scanned for music links.")
    @app_commands.describe(channel="Channel to watch for shared music links")
    async def set_music_channel(self, interaction: Interaction, channel: discord.TextChannel) -> None:
        """Configura el canal donde se auto-detectan los enlaces de música."""
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return
        await db.update_settings(interaction.guild_id, music_channel_id=str(channel.id))
        await interaction.response.send_message(f"✅ Music links channel set to: {channel.mention}.", ephemeral=True)

    @settings_group.command(name="music_battle_channel", description="Set the channel for music battles, reclaims and Song of the Day.")
    @app_commands.describe(channel="Channel where battles and SOTD are posted")
    async def set_music_battle_channel(self, interaction: Interaction, channel: discord.TextChannel) -> None:
        """Configura el canal de batallas musicales, reclaims y Canción del Día."""
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return
        await db.update_settings(interaction.guild_id, music_battle_channel_id=str(channel.id))
        await interaction.response.send_message(f"✅ Music battle channel set to: {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Settings(bot))
