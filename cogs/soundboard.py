import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

AUDIO_DIR = "audio"

class Soundboard(commands.Cog, name="Soundboard"):
    """Dame un gur"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_sounds(self) -> list[str]:
        """Un que?"""
        if not os.path.isdir(AUDIO_DIR):
            return []
        return [
            os.path.splitext(f)[0]
            for f in os.listdir(AUDIO_DIR)
            if f.endswith((".mp3", ".wav", ".ogg"))
        ]

    async def _play_in_channel(
        self,
        interaction: discord.Interaction,
        sound_path: str,
        sound_name: str,
        target_channel: discord.VoiceChannel
    ):
        """Un gur un gur"""
        for existing_vc in self.bot.voice_clients:
            if existing_vc.guild == interaction.guild:
                await existing_vc.disconnect(force=True)

        try:
            vc = await target_channel.connect()
        except discord.ClientException as e:
            await interaction.followup.send(f"❌ No se pudo conectar al canal: {e}", ephemeral=True)
            return

        print(f"Tusmu in {sound_path} gurt? {target_channel.name}")

        try:
            ffmpeg_opts = {
                'executable': 'ffmpeg',
                'options': '-vn'
            }
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(sound_path, **ffmpeg_opts),
                volume=1.0
            )
            vc.play(
                source,
                after=lambda e: self.bot.loop.create_task(self._disconnect(vc, e))
            )
        except Exception as e:
            print(f"[Soundboard] vc.play exception: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            await vc.disconnect()
            return

        await interaction.followup.send(
            f"🔊 Mumuk `{sound_name}` en **{target_channel.name}**... 💀"
        )

    @app_commands.command(
        name="play",
        description="Dale un gurt"
    )
    @app_commands.describe(
        sound="?",
        channel="vc (optional)",
        user="user (optional)"
    )
    async def play(
        self,
        interaction: discord.Interaction,
        sound: str,
        channel: Optional[discord.VoiceChannel] = None,
        user: Optional[discord.Member] = None,
    ):
        await interaction.response.defer()

        target_channel: discord.VoiceChannel | None = None

        if channel is not None:
            target_channel = channel
        elif user is not None:
            if user.voice and user.voice.channel:
                target_channel = user.voice.channel
            else:
                await interaction.followup.send(
                    f"❌ {user.mention}, el gitano este no esta en ningun canal.",
                    ephemeral=True
                )
                return
        else:
            if interaction.user.voice and interaction.user.voice.channel:
                target_channel = interaction.user.voice.channel
            else:
                await interaction.followup.send(
                    "❌ Error 67",
                    ephemeral=True
                )
                return

        sound_path = None
        for ext in (".mp3", ".wav", ".ogg"):
            candidate = os.path.join(AUDIO_DIR, sound + ext)
            if os.path.isfile(candidate):
                sound_path = candidate
                break

        if not sound_path:
            available = ", ".join(self.get_sounds()) or "ninguno"
            await interaction.followup.send(
                f"❌ Sonido `{sound}` no encontrado. Disponible ahora: `{available}`",
                ephemeral=True
            )
            return

        await self._play_in_channel(interaction, sound_path, sound, target_channel)

    async def _disconnect(self, vc: discord.VoiceClient, error):
        """Desvincula"""
        if error:
            print(f"[Soundboard] Playback error: {error}")
        await asyncio.sleep(0.5)
        if vc.is_connected():
            await vc.disconnect()

    @app_commands.command(name="sounds", description="Disponibilidad")
    async def sounds(self, interaction: discord.Interaction):
        available = self.get_sounds()
        if not available:
            await interaction.response.send_message("😔 No hay sonidos disponibles.", ephemeral=True)
            return
        embed = discord.Embed(
            title="🎵 Sonidos disponibles",
            description="\n".join(f"• `{s}`" for s in available),
            color=discord.Color.purple()
        )
        embed.set_footer(text="Usa /play <nombre> para reproducir un sonido.")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Soundboard(bot))
