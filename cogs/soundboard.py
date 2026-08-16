import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

DEFAULT_AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio")
AUDIO_DIR = os.getenv("AUDIO_DIR", DEFAULT_AUDIO_DIR)

FFMPEG_OPTIONS = {
    'executable': '/usr/bin/ffmpeg',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -ar 48000 -ac 2 -f s16le'
}


class Soundboard(commands.Cog, name="Soundboard"):
    """Reproduce sonidos locales en canales de voz (/play, /sounds)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def get_sounds(self) -> list[str]:
        """Devuelve los nombres de los sonidos disponibles."""
        if not os.path.isdir(AUDIO_DIR):
            return []
        return [
            os.path.splitext(f)[0]
            for f in os.listdir(AUDIO_DIR)
            if f.endswith((".mp3", ".wav", ".ogg", ".pcm"))
        ]

    async def _play_in_channel(
        self,
        interaction: discord.Interaction,
        sound_path: str,
        sound_name: str,
        target_channel: discord.VoiceChannel
    ) -> None:
        """Conecta al canal y reproduce el sonido indicado."""
        for existing_vc in self.bot.voice_clients:
            if existing_vc.guild == interaction.guild:
                await existing_vc.disconnect(force=True)

        try:
            vc = await target_channel.connect()
        except discord.ClientException as e:
            await interaction.followup.send(f"❌ Couldn't connect: {e}", ephemeral=True)
            return

        print(f"[Soundboard] Playing {sound_path} in {target_channel.name}")

        try:
            source = discord.FFmpegPCMAudio(
                sound_path,
                executable='/usr/bin/ffmpeg',
                before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                options='-vn -ar 48000 -ac 2 -f s16le pipe:1'
            )
            transformed = discord.PCMVolumeTransformer(source, volume=1.0)
            vc.play(
                transformed,
                after=lambda e: self.bot.loop.create_task(self._disconnect(vc, e))
            )
        except Exception as e:
            print(f"[Soundboard] vc.play exception: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            await vc.disconnect()
            return

        await interaction.followup.send(
            f"🔊 `{sound_name}` in **{target_channel.name}**"
        )

    @app_commands.command(
        name="play",
        description="Dame un grr"
    )
    @app_commands.describe(
        sound="...",
        channel="(opcional)",
        user="(opcional)"
    )
    async def play(
        self,
        interaction: discord.Interaction,
        sound: str,
        channel: Optional[discord.VoiceChannel] = None,
        user: Optional[discord.Member] = None,
    ) -> None:
        """Reproduce un sonido en un canal de voz (o en el del usuario indicado)."""
        await interaction.response.defer()

        target_channel = None

        if channel is not None:
            target_channel = channel
        elif user is not None:
            if user.voice and user.voice.channel:
                target_channel = user.voice.channel
            else:
                await interaction.followup.send(
                    f"❌ {user.mention} isn't in a vc.",
                    ephemeral=True
                )
                return
        else:
            if isinstance(interaction.user, discord.Member) and interaction.user.voice and interaction.user.voice.channel:
                target_channel = interaction.user.voice.channel
            else:
                await interaction.followup.send(
                    "❌ You must be in a channel or specify options.",
                    ephemeral=True
                )
                return

        sound_path = None
        for ext in (".mp3", ".wav", ".ogg", ".pcm"):
            candidate = os.path.join(AUDIO_DIR, sound + ext)
            if os.path.isfile(candidate):
                sound_path = candidate
                break

        if not sound_path:
            available = ", ".join(self.get_sounds()) or "ninguno"
            await interaction.followup.send(
                f"❌ Sound `{sound}` not found.\n🎵 Available: `{available}`",
                ephemeral=True
            )
            return

        await self._play_in_channel(interaction, sound_path, sound, target_channel)

    async def _disconnect(self, vc: discord.VoiceClient, error: Exception | None) -> None:
        """Desconecta el cliente de voz tras la reproducción."""
        if error:
            print(f"[Soundboard] Playback error: {error}")
        await asyncio.sleep(0.5)
        if vc.is_connected():
            await vc.disconnect()

    @app_commands.command(name="sounds", description="Un que?")
    async def sounds(self, interaction: discord.Interaction) -> None:
        """Lista los sonidos disponibles."""
        available = self.get_sounds()
        if not available:
            await interaction.response.send_message("No available sounds.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Available sounds",
            description="\n".join(f"• `{s}`" for s in available),
            color=discord.Color.purple()
        )
        embed.set_footer(text="Use /play <sound_name>")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Soundboard(bot))
