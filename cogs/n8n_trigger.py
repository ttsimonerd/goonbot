"""
/trigger — fires an HTTP POST at a configured n8n webhook URL so a workflow
can be started directly from Discord.
"""

import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")


class N8N(commands.Cog, name="N8N"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="trigger", description="Dispara el workflow de n8n configurado.")
    @app_commands.describe(data="Texto opcional para enviar al workflow (queda disponible en el JSON body)")
    async def trigger(self, interaction: discord.Interaction, data: str = None):
        if not N8N_WEBHOOK_URL:
            await interaction.response.send_message(
                "❌ N8N_WEBHOOK_URL no está configurado en el bot.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        payload = {
            "triggered_by": str(interaction.user),
            "discord_id": str(interaction.user.id),
            "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
            "data": data,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    N8N_WEBHOOK_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status < 400:
                        # Success — n8n's own Discord node sends the actual
                        # reply, so we just clear our "thinking..." placeholder.
                        await interaction.delete_original_response()
                    else:
                        body_preview = (await resp.text())[:300]
                        await interaction.followup.send(
                            f"⚠️ n8n respondió con error {resp.status}: {body_preview}", ephemeral=True
                        )
        except aiohttp.ClientError as e:
            await interaction.followup.send(f"❌ No se pudo contactar con n8n: {e}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error inesperado: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(N8N(bot))
