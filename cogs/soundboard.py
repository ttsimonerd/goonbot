import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands

# Lists all audio files in audio/ so users can discover them
AUDIO_DIR = "audio"


class Soundboard(commands.Cog, name="Soundboard"):
    """Commandos para reproducir sonidos en canales de voz."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_sounds(self) -> list[str]:
        """Returns list of available sound names (without extension)."""
        if not os.path.isdir(AUDIO_DIR):
            return []
        return [
            os.path.splitext(f)[0]
            for f in os.listdir(AUDIO_DIR)
            if f.endswith((".mp3", ".wav", ".ogg"))
        ]

    @app_commands.command(name="play", description="Reproduce un sonido en tu canal de voz.")
    @app_commands.describe(sound="Nombre del sonido a reproducir")
    async def play(self, interaction: discord.Interaction, sound: str):
        # Must be in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ Debes estar en un canal de voz para usar este comando.", ephemeral=True
            )
            return

        # Find the file
        sound_path = None
        for ext in (".mp3", ".wav", ".ogg"):
            candidate = os.path.join(AUDIO_DIR, sound + ext)
            if os.path.isfile(candidate):
                sound_path = candidate
                break

        if not sound_path:
            available = ", ".join(self.get_sounds()) or "ninguno"
            await interaction.response.send_message(
                f"❌ Sonido `{sound}` no encontrado.\n🎵 Disponibles: `{available}`",
                ephemeral=True
            )
            return

        await interaction.response.send_message(f"🔊 Reproduciendo `{sound}`...")

        voice_channel = interaction.user.voice.channel

        try:
            # Connect to voice channel
            vc = await voice_channel.connect()

            # Play the audio
            vc.play(
                discord.FFmpegPCMAudio(sound_path),
                after=lambda e: self.bot.loop.create_task(self._disconnect(vc, e))
            )
        except discord.ClientException:
            # Already connected somewhere — disconnect and reconnect
            for vc in self.bot.voice_clients:
                await vc.disconnect(force=True)
            vc = await voice_channel.connect()
            vc.play(
                discord.FFmpegPCMAudio(sound_path),
                after=lambda e: self.bot.loop.create_task(self._disconnect(vc, e))
            )

    async def _disconnect(self, vc: discord.VoiceClient, error):
        """Disconnects from voice channel after audio finishes."""
        if error:
            print(f"[Soundboard] Playback error: {error}")
        await asyncio.sleep(0.5)  # Small buffer
        if vc.is_connected():
            await vc.disconnect()

    @app_commands.command(name="sounds", description="Lista todos los sonidos disponibles.")
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
