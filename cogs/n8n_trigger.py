import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")


class N8N(commands.Cog, name="N8N"):
    """Comando /pluh que dispara un webhook de n8n."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="pluh", description="Random")
    async def trigger(self, interaction: discord.Interaction) -> None:
        """Dispara el webhook de n8n configurado."""
        if not N8N_WEBHOOK_URL:
            await interaction.response.send_message(
                "❌ Request error: N8N_WEBHOOK_URL not configured", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        payload = {
            "triggered_by": str(interaction.user),
            "discord_id": str(interaction.user.id),
            "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    N8N_WEBHOOK_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status < 400:
                        await interaction.followup.send("⚡ Triggered successfully!", ephemeral=True)
                    else:
                        body_preview = (await resp.text())[:300]
                        await interaction.followup.send(
                            f"⚠️ HTTP {resp.status}: {body_preview}", ephemeral=True
                        )
        except aiohttp.ClientError as e:
            await interaction.followup.send(f"❌ Connection error: {e}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(N8N(bot))
