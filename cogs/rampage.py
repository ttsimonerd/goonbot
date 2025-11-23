# cogs/rampage.py
import discord
from discord.ext import commands
import asyncio
from pathlib import Path
from discord import FFmpegPCMAudio
from discord import PCMVolumeTransformer

# Ajusta la ruta si quieres otro nombre/ubicación
AUDIO_PATH = Path("audio/rampage.mp3")
# Volumen por defecto (1.0 = 100%)
DEFAULT_VOLUME = 1.0

class Rampage(commands.Cog):
    """RAMPAGE"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="rampage")
    async def rampage(self, ctx: commands.Context, member: discord.Member = None):
        """
        ^rampage
        ^rampage @User

        Si el autor está en canal de voz, el bot se une a ese canal. Si no,
        puede recibir un miembro como objetivo para unirse a su canal (si está en uno).
        Reproduce audio local y luego se desconecta.
        """
        
        target = member or ctx.author

        # target?
        if not target.voice or not target.voice.channel:
            await ctx.send("No estás en un canal de voz o no has especificado a nadie.")
            return

        channel = target.voice.channel

        # Connect
        voice_client: discord.VoiceClient = ctx.voice_client

        try:
            if voice_client and voice_client.is_connected():
                
                if voice_client.channel.id != channel.id:
                    await voice_client.move_to(channel)
            else:
                # Model Connect
                voice_client = await channel.connect(self_deaf=True)
        except discord.Forbidden:
            await ctx.send("No tengo permisos :(")
            return
        except discord.ClientException:
            # Reference
            voice_client = ctx.voice_client
            if voice_client is None:
                await ctx.send("Error al conectar :(")
                return

        await ctx.send(f"Channel: **{channel.name}**")

        await asyncio.sleep(2)

        # Comprobar archivo de audio
        if not AUDIO_PATH.exists():
            await ctx.send("ERROR: File Didn't Load")
            # Intentamos desconectar si estamos conectados
            try:
                if voice_client and voice_client.is_connected():
                    await voice_client.disconnect()
            except Exception:
                pass
            return

        # Preparar fuente de audio (FFmpeg) y opcionalmente volumen
        # Asegúrate de que FFmpeg esté instalado en el host
        ffmpeg_options = {
            "before_options": "-nostdin",
            "options": "-vn"
        }

        source = FFmpegPCMAudio(str(AUDIO_PATH), **ffmpeg_options)
        player = PCMVolumeTransformer(source, volume=DEFAULT_VOLUME)

        try:
            # Reproducir
            voice_client.play(player)
            await ctx.send("...")
        except Exception as e:
            await ctx.send(f"Error al reproducir: {e}")
            try:
                if voice_client and voice_client.is_connected():
                    await voice_client.disconnect()
            except Exception:
                pass
            return

        # Esperar a que termine la reproducción
        while voice_client.is_playing():
            await asyncio.sleep(1)

        # Desconectar al terminar
        try:
            await voice_client.disconnect()
        except Exception:
            pass

        await ctx.send("Exiting...")

async def setup(bot: commands.Bot):
    await bot.add_cog(Rampage(bot))
