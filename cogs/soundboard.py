import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

# Lists all audio files in audio/ so users can discover them
AUDIO_DIR = "audio"


class Soundboard(commands.Cog, name="Soundboard"):
    """Comandos para reproducir sonidos en canales de voz."""

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

    async def _play_in_channel(
        self,
        interaction: discord.Interaction,
        sound_path: str,
        sound_name: str,
        target_channel: discord.VoiceChannel
    ):
        """Core logic: connect to target_channel, play audio, disconnect."""
        # Disconnect from any existing voice connection first
        for existing_vc in self.bot.voice_clients:
            if existing_vc.guild == interaction.guild:
                await existing_vc.disconnect(force=True)

        try:
            vc = await target_channel.connect()
        except discord.ClientException as e:
            await interaction.followup.send(f"❌ No se pudo conectar al canal: {e}", ephemeral=True)
            return

        vc.play(
            discord.FFmpegPCMAudio(sound_path),
            after=lambda e: self.bot.loop.create_task(self._disconnect(vc, e))
        )

        await interaction.followup.send(
            f"🔊 Reproduciendo `{sound_name}` en **{target_channel.name}**... 💀"
        )

    @app_commands.command(
        name="play",
        description="Reproduce un sonido en un canal de voz. ¡Perfecto para bromear!"
    )
    @app_commands.describe(
        sound="Nombre del sonido a reproducir",
        channel="Canal de voz donde reproducir (opcional)",
        user="Reproduce en el canal de voz donde está este usuario (opcional)"
    )
    async def play(
        self,
        interaction: discord.Interaction,
        sound: str,
        channel: Optional[discord.VoiceChannel] = None,
        user: Optional[discord.Member] = None,
    ):
        await interaction.response.defer()

        # --- Resolve target voice channel (priority: channel > user > self) ---
        target_channel: discord.VoiceChannel | None = None

        if channel is not None:
            # Explicit channel provided
            target_channel = channel

        elif user is not None:
            # Join wherever the target user is
            if user.voice and user.voice.channel:
                target_channel = user.voice.channel
            else:
                await interaction.followup.send(
                    f"❌ {user.mention} no está en ningún canal de voz ahora mismo.",
                    ephemeral=True
                )
                return

        else:
            # Fallback: join the command author's channel
            if interaction.user.voice and interaction.user.voice.channel:
                target_channel = interaction.user.voice.channel
            else:
                await interaction.followup.send(
                    "❌ Debes estar en un canal de voz, o especificar un `canal` o `usuario`.",
                    ephemeral=True
                )
                return

        # --- Find the sound file ---
        sound_path = None
        for ext in (".mp3", ".wav", ".ogg"):
            candidate = os.path.join(AUDIO_DIR, sound + ext)
            if os.path.isfile(candidate):
                sound_path = candidate
                break

        if not sound_path:
            available = ", ".join(self.get_sounds()) or "ninguno"
            await interaction.followup.send(
                f"❌ Sonido `{sound}` no encontrado.\n🎵 Disponibles: `{available}`",
                ephemeral=True
            )
            return

        # --- Play it ---
        await self._play_in_channel(interaction, sound_path, sound, target_channel)

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
