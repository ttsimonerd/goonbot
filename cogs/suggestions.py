import discord
from discord import app_commands, ui, Interaction
from discord.ext import commands

import db


# ---------------------
# Modal
# ---------------------
class SuggestionModal(ui.Modal, title="💡 New suggestion"):
    suggestion_title = ui.TextInput(
        label="Title",
        placeholder="Example: Add a command to...",
        required=True,
        max_length=100
    )
    suggestion_body = ui.TextInput(
        label="Description (optional)",
        placeholder="Detailed idea description...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "❌ Suggestions can only be submitted inside a server.",
                ephemeral=True
            )
            return

        settings = await db.get_settings(guild.id)
        ch_id = settings.get("suggestions_channel_id")

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
                "❌ No suggestion channel found. If you are admin, set it with `/settings suggestions_channel`.",
                ephemeral=True
            )
            return

        # Build the embed
        embed = discord.Embed(
            title=f"💡 {self.suggestion_title.value}",
            description=self.suggestion_body.value or "*No additional description*",
            color=discord.Color.gold()
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
        )
        embed.set_footer(text=f"{interaction.user}'s suggestion • ID: {interaction.user.id}")

        # Post it to the suggestions channel with voting reactions
        msg = await suggestions_channel.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        await interaction.response.send_message(
            "✅ Your suggestion has been sent!",
            ephemeral=True
        )

    async def on_error(self, interaction: Interaction, error: Exception):
        await interaction.response.send_message(
            f"⚠️ Error: {error}", ephemeral=True
        )


class Suggestions(commands.Cog, name="Suggestions"):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="suggest", description="Send a suggestion")
    async def suggest(self, interaction: Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return
        modal = SuggestionModal(self.bot)
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot):
    await bot.add_cog(Suggestions(bot))
