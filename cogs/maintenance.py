import os
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

DISCORD_CHANNEL_ID = 1438967391513219132
RCON_HOST = "localhost"
RCON_PORT = 25575

async def run_mc_command(command: str):
    proc = await __import__('asyncio').create_subprocess_shell(
        f"sudo docker exec minecraft-f1p4dva1nj1mnqfd45slwcov rcon-cli {command}",
        stdout=__import__('asyncio').subprocess.PIPE,
        stderr=__import__('asyncio').subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode().strip()

class Maintenance(commands.Cog, name="Maintenance"):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.maintenance_mode = False

    @app_commands.command(name="maintenance", description="[DEV]")
    @app_commands.describe(mode="on/off")
    @app_commands.choices(mode=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off")
    ])
    @app_commands.default_permissions(administrator=True)
    async def maintenance(self, interaction: discord.Interaction, mode: str):
        await interaction.response.defer(ephemeral=True)

        channel = self.bot.get_channel(DISCORD_CHANNEL_ID)

        if mode == "on":
            self.maintenance_mode = True

            # Enable whitelist and add admin
            await run_mc_command("whitelist on")
            await run_mc_command("whitelist add tt_simoner")
            await run_mc_command("kickall Servidor en mantenimiento. Vuelve pronto!")

            # Discord message
            embed = discord.Embed(
                title="🔧 Servidor en Mantenimiento",
                description="El servidor **Sapadas** está actualmente en mantenimiento y no es accesible.\n\nVuelve más tarde! 🙏",
                color=discord.Color.orange()
            )
            embed.set_footer(text="Sapadas Minecraft Server")

            if channel:
                await channel.send(embed=embed)

            await interaction.followup.send("✅ Modo mantenimiento **activado**.", ephemeral=True)

        elif mode == "off":
            self.maintenance_mode = False

            # Disable whitelist
            await run_mc_command("whitelist off")

            # Discord message
            embed = discord.Embed(
                title="✅ Servidor Abierto",
                description="El servidor **Sapadas** ya está disponible!",
                color=discord.Color.green()
            )
            embed.set_footer(text="Sapadas Minecraft Server")

            if channel:
                await channel.send(embed=embed)

            await interaction.followup.send("✅ Modo mantenimiento **desactivado**.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Maintenance(bot))
