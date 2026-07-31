import discord
from discord import app_commands, Interaction
from discord.ext import commands

import db


class Settings(commands.Cog, name="Settings"):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    settings_group = app_commands.Group(
        name="settings",
        description="[ADMIN]",
        default_permissions=discord.Permissions(administrator=True)
    )

    @settings_group.command(name="view", description="Show current config")
    async def view(self, interaction: Interaction):
        data = await db.get_settings(interaction.guild_id)

        gambling_ch = interaction.guild.get_channel(data["gambling_channel_id"]) if data["gambling_channel_id"] else None
        suggestions_ch = interaction.guild.get_channel(data["suggestions_channel_id"]) if data["suggestions_channel_id"] else None
        winning_ch = interaction.guild.get_channel(data["gambling_winners_channel_id"]) if data["gambling_winners_channel_id"] else None

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
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="gambling_channel", description="Set gambling channel.")
    @app_commands.describe(channel="Gambling channel")
    async def set_gambling_channel(self, interaction: Interaction, channel: discord.TextChannel):
        await db.update_settings(interaction.guild_id, gambling_channel_id=str(channel.id))
        await interaction.response.send_message(f"✅ Channel set to: {channel.mention}.", ephemeral=True)

    @settings_group.command(name="suggestions_channel", description="Set suggestions channel.")
    @app_commands.describe(channel="Suggestions channel")
    async def set_suggestions_channel(self, interaction: Interaction, channel: discord.TextChannel):
        await db.update_settings(interaction.guild_id, suggestions_channel_id=str(channel.id))
        await interaction.response.send_message(f"✅ Channel set to: {channel.mention}.", ephemeral=True)

    @settings_group.command(name="winners_channel", description="Set daily wins channel.")
    @app_commands.describe(channel="Daily wins channel")
    async def set_winners_channel(self, interaction: Interaction, channel: discord.TextChannel):
        await db.update_settings(interaction.guild_id, gambling_winners_channel_id=str(channel.id))
        await interaction.response.send_message(f"✅ Channel set to: {channel.mention}.", ephemeral=True)

    @settings_group.command(name="lockout_hours", description="Set timeout gambling hours.")
    @app_commands.describe(hours="Minimum 1 hour")
    async def set_lockout_hours(self, interaction: Interaction, hours: int):
        if hours < 1:
            await interaction.response.send_message("❌ Minimum 1 hour nih", ephemeral=True)
            return
        await db.update_settings(interaction.guild_id, gambling_lockout_hours=hours)
        await interaction.response.send_message(f"✅ Gambling ban now lasts: **{hours} hours**.", ephemeral=True)

    @settings_group.command(name="max_warns", description="Set maximum warns before ban.")
    @app_commands.describe(warns="Minimum 1")
    async def set_max_warns(self, interaction: Interaction, warns: int):
        if warns < 1:
            await interaction.response.send_message("❌ Minimum 1 nih", ephemeral=True)
            return
        await db.update_settings(interaction.guild_id, gambling_max_warns=warns)
        await interaction.response.send_message(f"✅ Maximum warns before ban set to: **{warns} warns**.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
