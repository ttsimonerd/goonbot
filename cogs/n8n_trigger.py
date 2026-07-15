import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")


class N8N(commands.Cog, name="N8N"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pluh", description="Random")
    async def trigger(self, interaction: discord.Interaction):
        if not N8N_WEBHOOK_URL:
            await interaction.response.send_message(
                "❌ Request error", ephemeral=True
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
                        await interaction.delete_original_response()
                    else:
                        body_preview = (await resp.text())[:300]
                        await interaction.followup.send(
                            f"⚠️ {resp.status}: {body_preview}", ephemeral=True
                        )
        except aiohttp.ClientError as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(N8N(bot))
