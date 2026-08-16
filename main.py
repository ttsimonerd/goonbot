import os
import signal
import logging
import contextlib
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import requests
import secrets
import db
from config import GUILD_ID, REDEPLOY_PASSWORD, WEBHOOK_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# The dashboard membership checks need the members intent, and the music
# link-scanner reads message content to auto-add songs users share.
# Presence intent is intentionally not requested.
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class GoonBot(commands.Bot):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Background tasks created across cogs (gambling loops, voice cleanup,
        # pending unlock timers) so we can cancel them all on shutdown.
        self._background_tasks: set[asyncio.Task] = set()

    def create_background_task(self, coro) -> asyncio.Task:
        """Schedule a coroutine and remember it for graceful shutdown."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def cancel_background_tasks(self) -> None:
        """Cancel and await every tracked background task."""
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def setup_hook(self) -> None:
        # Route unhandled task/loop exceptions (background loops, voice
        # playback "after" callbacks, etc.) to our logging handler.
        asyncio.get_running_loop().set_exception_handler(self._handle_loop_exception)

        extensions = [
            "cogs.music",
            "cogs.admin",
            "cogs.fun",
            "cogs.gambling",
            "cogs.mensajes",
            "cogs.settings",
            "cogs.soundboard",
            "cogs.suggestions"
        ]

        for ext in extensions:
            try:
                await self.load_extension(ext)
                logger.info("✅ Loaded extension: %s", ext)
            except Exception as e:
                logger.error("❌ Failed to load extension %s: %s", ext, e)

        # -----------------------------------------------------
        # Slash command synchronization
        # -----------------------------------------------------

        logger.info("==== TREE BEFORE SYNC ====")

        local_cmds = list(self.tree.walk_commands())
        logger.info("Total commands in tree: %d", len(local_cmds))
        for cmd in local_cmds:
            logger.info("  - %s", cmd.qualified_name)

        logger.info("==========================")

        guild = discord.Object(id=GUILD_ID)

        try:
            # Rebuild the guild's command list from scratch so commands we
            # removed in code actually disappear, then push it to the guild.
            self.tree.clear_commands(guild=guild)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)

            logger.info("===== REGISTERED GUILD COMMANDS (%d) =====", len(synced))

            for cmd in synced:
                logger.info("  - %s", cmd.name)

            logger.info("===============================")

            # This bot serves a single guild, so drop the global copies and
            # sync an empty global list. That deletes any global commands left
            # over by older deploys — otherwise every command shows up twice
            # in the / picker (once global, once guild).
            self.tree.clear_commands(guild=None)
            await self.tree.sync(guild=None)

        except Exception as e:
            logger.error("❌ Sync error: %s", e)

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
        logger.error("App command error in %s: %r", command_name, error)

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
            logger.error(
                "Unexpected error in command %s",
                command_name,
                exc_info=(type(error), error, error.__traceback__),
            )

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
        logger.error("Unhandled exception in %s", event_method, exc_info=True)

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
            logger.error(
                "Unhandled task exception",
                exc_info=(type(exception), exception, exception.__traceback__),
            )
        else:
            logger.error("%s", context.get("message", "unknown error"))


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
    logger.info("Bot conectado, %s", bot.user)


# -----------------------------------------------------
# Basicos
# -----------------------------------------------------

@bot.tree.command(name="ping", description="Comprueba si el bot está vivo")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(
        "¡Hola! Estoy funcionando y siendo hosteado en el server de ttsmcz RPI5.\n"
        f"🏓 Latencia: {latency} ms"
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
            "`/ping` — Comprueba si el bot está vivo\n"
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
        name="⚙️ Configuración `/` *(Admin)*",
        value=(
            "`/settings view` — Ver configuración actual\n"
            "`/settings gambling_channel #canal` — Cambiar canal de gambling\n"
            "`/settings winners_channel #canal` — Cambiar canal de ganadores diarios\n"
            "`/settings suggestions_channel #canal` — Cambiar canal de sugerencias\n"
            "`/settings music_channel #canal` — Canal de enlaces de música\n"
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
        text="Goonbot • Hosteado por ttsmcz"
    )

    await interaction.response.send_message(embed=embed)


# -----------------------------------------------------
# Redeploy
# -----------------------------------------------------

@bot.tree.command(name="redeploy", description="Redeploy webhook. Dev only!")
@app_commands.describe(password="OAuth")
async def sendwebhook(interaction: discord.Interaction, password: str):
    if not REDEPLOY_PASSWORD or not secrets.compare_digest(password, REDEPLOY_PASSWORD):
        await interaction.response.send_message(
            "Access denied.",
            ephemeral=True
        )
        return

    if not WEBHOOK_URL:
        await interaction.response.send_message(
            "❌ WEBHOOK_DEP no está configurado.",
            ephemeral=True
        )
        return

    try:
        response = requests.post(WEBHOOK_URL, timeout=30)
        response.raise_for_status()

        await interaction.response.send_message(
            "Request sent! Re-deploying..."
        )

    except requests.RequestException as e:
        logger.error("Error sending webhook: %s", e)

        await interaction.response.send_message(
            "Failed to send request.",
            ephemeral=True
        )


# -----------------------------------------------------
# Main
# -----------------------------------------------------

async def run_services(token: str) -> None:
    """Run the Discord bot and the dashboard together until shutdown.

    The two services are started as independent tasks so a crash in one does
    not take the other down with it: a dashboard failure is logged while the
    bot keeps running, and a bot failure triggers a full graceful shutdown.
    """
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

    # SIGINT / SIGTERM -> graceful shutdown instead of asyncio.run() cancelling
    # tasks mid-flight (which could interrupt a DB write).
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _request_shutdown(sig: signal.Signals) -> None:
        logger.info("Received %s, shutting down gracefully...", sig.name)
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown, sig)
        except NotImplementedError:
            # add_signal_handler is unavailable on some platforms (Windows).
            pass

    bot_task: asyncio.Task | None = None
    server_task: asyncio.Task | None = None

    try:
        async with bot:
            bot_task = asyncio.create_task(bot.start(token), name="discord-bot")
            server_task = asyncio.create_task(server.serve(), name="dashboard")
            shutdown_task = asyncio.create_task(shutdown_event.wait(), name="shutdown-watch")

            pending = {bot_task, server_task, shutdown_task}
            stop = False

            # Wait for the first thing to happen: a signal, or either service
            # finishing on its own. asyncio.wait() does not re-raise a task's
            # exception, so a crash here can't cancel the other service.
            while pending and not stop:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    if task is shutdown_task:
                        stop = True
                        break
                    exc = task.exception()
                    if exc is not None:
                        logger.error(
                            "%s crashed",
                            task.get_name(),
                            exc_info=(type(exc), exc, exc.__traceback__),
                        )
                    if task is bot_task:
                        # The bot going down takes the whole process with it.
                        stop = True
                        break
                    # Only the dashboard stopped on its own: log and keep the
                    # bot running.
                    logger.warning("%s stopped; the bot keeps running.", task.get_name())
    finally:
        # Stop the dashboard first so no new requests arrive mid-teardown,
        # giving in-flight requests a moment to finish.
        if server_task is not None and not server_task.done():
            server.should_exit = True
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(server_task), timeout=10)

        # The bot is already closed (the `async with bot` block exited), so
        # cancel the background loops/timers before the event loop stops.
        await bot.cancel_background_tasks()


async def main() -> None:
    token = os.getenv("DISCORD_TOKEN")

    if not token:
        raise RuntimeError(
            "CRITICAL ERROR: DISCORD_TOKEN is missing or not set in environment variables!"
        )

    try:
        await db.init_db()
        await db.ensure_api_key_seeded()
        logger.info("✅ Database initialized")
        await run_services(token)
    finally:
        await db.close_db()
        logger.info("👋  Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())