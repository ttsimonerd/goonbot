import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

AUDIO_DIR = "/app/audio"

FFMPEG_OPTIONS = {
    'executable': '/usr/bin/ffmpeg',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -ar 48000 -ac 2 -f s16le'
}

class Soundboard(commands.Cog, name="Soundboard"):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_sounds(self) -> list[str]:
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
    ):
        for existing_vc in self.bot.voice_clients:
            if existing_vc.guild == interaction.guild:
                await existing_vc.disconnect(force=True)

        try:
            vc = await target_channel.connect()
        except discord.ClientException as e:
            await interaction.followup.send(f"❌ No se pudo conectar al canal: {e}", ephemeral=True)
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
            f"🔊 `{sound_name}` en **{target_channel.name}**"
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
    ):
        await interaction.response.defer()

        target_channel = None

        if channel is not None:
            target_channel = channel
        elif user is not None:
            if user.voice and user.voice.channel:
                target_channel = user.voice.channel
            else:
                await interaction.followup.send(
                    f"❌ {user.mention} no está en ningún canal de voz.",
                    ephemeral=True
                )
                return
        else:
            if interaction.user.voice and interaction.user.voice.channel:
                target_channel = interaction.user.voice.channel
            else:
                await interaction.followup.send(
                    "❌ Debes estar en un canal de voz, o especificar un `canal` o `usuario`.",
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
                f"❌ Sonido `{sound}` no encontrado.\n🎵 Disponibles: `{available}`",
                ephemeral=True
            )
            return

        await self._play_in_channel(interaction, sound_path, sound, target_channel)

    async def _disconnect(self, vc: discord.VoiceClient, error):
        if error:
            print(f"[Soundboard] Playback error: {error}")
        await asyncio.sleep(0.5)
        if vc.is_connected():
            await vc.disconnect()

    @app_commands.command(name="sounds", description="Un que?")
    async def sounds(self, interaction: discord.Interaction):
        available = self.get_sounds()
        if not available:
            await interaction.response.send_message("No hay sonidos disponibles.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Sonidos disponibles",
            description="\n".join(f"• `{s}`" for s in available),
            color=discord.Color.purple()
        )
        embed.set_footer(text="Usa /play <nombre> para reproducir un sonido.")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Soundboard(bot))
