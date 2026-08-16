import os
import traceback
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import requests
import db
from config import GUILD_ID, REDEPLOY_PASSWORD, WEBHOOK_URL

# We only need the members intent (for the dashboard membership checks and
# member lookups). Message Content and Presence intents are intentionally NOT
# requested: Discord now treats message content as a deprecated privileged
# intent and pushes bots to use slash commands instead of prefix commands.
intents = discord.Intents.default()
intents.members = True

class GoonBot(commands.Bot):
    async def setup_hook(self) -> None:
        # Route unhandled task/loop exceptions (background loops, voice
        # playback "after" callbacks, etc.) to our logging handler.
        asyncio.get_running_loop().set_exception_handler(self._handle_loop_exception)

        extensions = [
            "cogs.music",
            "cogs.admin",
            "cogs.aitexts",
            "cogs.fun",
            "cogs.gambling",
            "cogs.maintenance",
            "cogs.mensajes",
            "cogs.n8n_trigger",
            "cogs.secret_command",
            "cogs.settings",
            "cogs.soundboard",
            "cogs.suggestions"
        ]

        for ext in extensions:
            try:
                await self.load_extension(ext)
                print(f"✅ Loaded extension: {ext}")
            except Exception as e:
                print(f"❌ Failed to load extension {ext}: {e}")

        # -----------------------------------------------------
        # Slash command synchronization
        # -----------------------------------------------------

        print("==== TREE BEFORE SYNC ====")

        local_cmds = list(self.tree.walk_commands())
        print(f"Total commands in tree: {len(local_cmds)}")
        for cmd in local_cmds:
            print(f"  - {cmd.qualified_name}")

        print("==========================")

        guild = discord.Object(id=GUILD_ID)

        try:
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)

            print(f"===== REGISTERED COMMANDS ({len(synced)}) =====")

            for cmd in synced:
                print(f"  - {cmd.name}")

            print("===============================")

        except Exception as e:
            print(f"❌ Sync error: {e}")

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        """Global slash-command error handler.

        Runs for any application command across every cog, so a failure never
        leaves the user with a silent "This interaction failed".
        """
        # CommandInvokeError wraps the real exception in .original.
        error = getattr(error, "original", error)

        command = interaction.command
        command_name = command.qualified_name if command else "unknown"
        print(f"[AppCommandError] {command_name}: {error!r}")

        # Map known failures to friendly Spanish messages.
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            message = f"⏳ Enfriamiento activo. Inténtalo de nuevo en {error.retry_after:.0f}s."
        elif isinstance(error, app_commands.errors.MissingPermissions):
            message = "❌ No tienes permisos para usar este comando."
        elif isinstance(error, app_commands.errors.BotMissingPermissions):
            message = f"❌ Me faltan permisos para hacer eso: {', '.join(error.missing_permissions)}."
        elif isinstance(error, app_commands.errors.NoPrivateMessage):
            message = "❌ Este comando solo funciona dentro de un servidor."
        elif isinstance(error, app_commands.errors.TransformerError):
            message = "❌ Valor inválido para uno de los argumentos."
        elif isinstance(error, app_commands.errors.CommandNotFound):
            message = "❌ Comando no encontrado."
        elif isinstance(error, app_commands.errors.CheckFailure):
            message = "❌ No tienes permiso para usar este comando."
        else:
            message = "❌ Ocurrió un error inesperado al ejecutar el comando."
            traceback.print_exception(type(error), error, error.__traceback__)

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception:
            # Interaction expired or its response was already fully used.
            pass

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        """Global handler for exceptions raised outside of commands.

        Catches failures from Discord event listeners (on_ready, on_message,
        voice events, and other gateway-dispatched callbacks) so they are
        logged instead of being silently swallowed. Slash-command errors are
        handled separately by on_app_command_error.
        """
        print(f"[EventError] Unhandled exception in {event_method}")
        traceback.print_exc()

    def _handle_loop_exception(
        self,
        loop: asyncio.AbstractEventLoop,
        context: dict,
    ) -> None:
        """Log unhandled asyncio task/loop exceptions.

        Covers code paths that on_error can't reach: background tasks started
        with asyncio.create_task() (the gambling loops, the soundboard's voice
        "after" callback, etc.).
        """
        exception = context.get("exception")
        if exception is not None:
            print("[LoopError] Unhandled task exception:")
            traceback.print_exception(type(exception), exception, exception.__traceback__)
        else:
            print(f"[LoopError] {context.get('message', 'unknown error')}")


bot = GoonBot(
    command_prefix="^",
    intents=intents,
    help_command=None
)


# -----------------------------------------------------
# Events
# -----------------------------------------------------

@bot.event
async def on_ready():
    print(f"Bot conectado, {bot.user}")


# -----------------------------------------------------
# Basicos
# -----------------------------------------------------

@bot.tree.command(name="hola", description="Comprueba si el bot está vivo")
async def hola(interaction: discord.Interaction):
    await interaction.response.send_message(
        "PONG! Btw estoy funcionando y siendo hosteado en el server de ttsmcz RPI5. "
        "(Alternativa a /ping)"
    )


@bot.tree.command(name="ping", description="Comprueba si el bot está vivo")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        "¡Hola! Estoy funcionando y siendo hosteado en el server de ttsmcz RPI5. "
        "(Alternativa a /hola)"
    )


@bot.tree.command(name="qtfn", description="Que te fakin nigger")
async def qtfn(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Que te fakin nigger {interaction.user.mention}"
    )


@bot.tree.command(name="help", description="Lista de comandos del bot")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Goonbot — Lista de Comandos",
        description="Todos los comandos usan `/` (comandos de barra).",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🔧 Básicos",
        value=(
            "`/hola` / `/ping` — Comprueba si el bot está vivo\n"
            "`/qtfn` — Que te fakin nigger\n"
            "`/help` — Esta ayuda"
        ),
        inline=False
    )

    embed.add_field(
        name="💬 Mensajes",
        value=(
            "`/message_add <mensaje>` — Guarda un mensaje\n"
            "`/message_list` — Lista los mensajes guardados\n"
            "`/edit_message` — Edita o elimina un mensaje tuyo"
        ),
        inline=False
    )

    embed.add_field(
        name="😂 Diversión",
        value=(
            "`/roast [@usuario]` — Insulta a alguien\n"
            "`/rape [@usuario]` — Amenaza a alguien\n"
            "`/rampage @usuario` — Rampage contra un usuario"
        ),
        inline=False
    )

    embed.add_field(
        name="🎲 Gambling `/`",
        value=(
            "`/roulette <red|black|even|odd|green>` — Juega a la ruleta\n"
            "`/blackjack` — Juega Blackjack\n"
            "`/poker` — Juega Poker rápido vs la banca\n"
            "`/crash` — Juego de rondas infinitas hasta perder o cobrar\n"
            "`/bet` — Apuesta dinero para ganar o perder\n"
            "`/balance [@usuario]` — Muestra saldo de gambling\n"
            "`/daily` — Reclama tu premio diario\n"
            "`/leaderboard` — Muestra el ranking de dinero\n"
            "`/votebet create <días> <predicción>` — Crea una apuesta personalizada\n"
            "`/votebet status` — Consulta tus apuestas activas\n"
            "`/gambling_warns [@usuario]` — Consulta warns de gambling\n"
            "`/gambling_pardon @usuario` — *(Admin)* Perdona warns"
        ),
        inline=False
    )

    embed.add_field(
        name="🔊 Soundboard `/`",
        value=(
            "`/play` — Reproduce un sonido en tu canal de voz\n"
            "`/play channel:#canal` — Reproduce en un canal de voz específico 🎯\n"
            "`/play user:@usuario` — Reproduce en el canal donde está ese usuario 😈\n"
            "`/sounds` — Lista los sonidos disponibles"
        ),
        inline=False
    )

    embed.add_field(
        name="💡 Sugerencias `/`",
        value="`/suggest` — Abre el formulario de sugerencias",
        inline=False
    )

    embed.add_field(
        name="🤖 IA `/`",
        value="`/lefa <mensaje>` — Habla con la IA",
        inline=False
    )

    embed.add_field(
        name="⚙️ Configuración `/` *(Admin)*",
        value=(
            "`/settings view` — Ver configuración actual\n"
            "`/settings gambling_channel #canal` — Cambiar canal de gambling\n"
            "`/settings winners_channel #canal` — Cambiar canal de ganadores diarios\n"
            "`/settings suggestions_channel #canal` — Cambiar canal de sugerencias\n"
            "`/settings lockout_hours` — Horas de ban por gambling\n"
            "`/settings max_warns` — Warns antes del ban"
        ),
        inline=False
    )

    embed.add_field(
        name="🔒 Admin `/`",
        value="`/redeploy` — (Dev only)",
        inline=False
    )

    embed.set_footer(
        text="Goonbot • Hosteado por ttsmcz • Powered by Local Ollama (Qwen2.5 0.5B)"
    )

    await interaction.response.send_message(embed=embed)


# -----------------------------------------------------
# Redeploy
# -----------------------------------------------------

@bot.tree.command(name="redeploy", description="Redeploy webhook. Dev only!")
@app_commands.describe(password="OAuth")
async def sendwebhook(interaction: discord.Interaction, password: str):
    if not REDEPLOY_PASSWORD or password != REDEPLOY_PASSWORD:
        await interaction.response.send_message(
            "Access denied.",
            ephemeral=True
        )
        return

    try:
        response = requests.post(WEBHOOK_URL)
        response.raise_for_status()

        await interaction.response.send_message(
            "Request sent! Re-deploying..."
        )

    except requests.RequestException as e:
        print(f"Error sending webhook: {e}")

        await interaction.response.send_message(
            "Failed to send request.",
            ephemeral=True
        )


# -----------------------------------------------------
# Main
# -----------------------------------------------------

async def main():
    token = os.getenv("DISCORD_TOKEN")

    if not token:
        raise RuntimeError(
            "CRITICAL ERROR: DISCORD_TOKEN is missing or not set in environment variables!"
        )

    await db.init_db()
    print("✅ Database initialized")

    from dashboard.app import create_app
    import uvicorn

    port = int(os.getenv("PORT", 8000))

    config = uvicorn.Config(
        create_app(bot),
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

    server = uvicorn.Server(config)

    async with bot:
        await asyncio.gather(
            bot.start(token),
            server.serve(),
        )


if __name__ == "__main__":
    asyncio.run(main())