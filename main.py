import os
import discord
from discord.ext import commands
from discord import app_commands
import json
import asyncio
import random
import aiohttp
import base64
from probabilities import roll_with_limit
import requests
import db

intents = discord.Intents.all()
intents.message_content = True

# -----------------------------------------------------
# Prefix, variables & things...
# -----------------------------------------------------

GUILD_ID = 1417556208767733823


class GoonBot(commands.Bot):
    async def setup_hook(self):
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

        for cmd in self.tree.walk_commands():
            print(cmd.qualified_name)

        print("==========================")

        guild = discord.Object(id=GUILD_ID)

        try:
            synced = await self.tree.sync(guild=guild)

            print("===== REGISTERED COMMANDS =====")

            for cmd in synced:
                print(cmd.name)

            print("===============================")

        except Exception as e:
            print(f"❌ Sync error: {e}")


bot = GoonBot(
    command_prefix="^",
    intents=intents,
    help_command=None
)


IMAGE_URLS = [
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745012944956/IMG_20251123_223528.jpg?ex=692578c2&is=69242742&hm=4b47769727c1751c0f1af171968e04cbe134e6c494a87811b7d6c1044d49b7e2",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745344426136/IMG_20251123_223600.jpg?ex=692578c2&is=69242742&hm=2abd81e14fc934758414968a69baf6f4eca971f094adabc7a9cfc37b44da663",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745986285749/IMG_20251123_223634.jpg?ex=692578c2&is=69242742&hm=115629a925ba57951db272b46001940669e6d2928b077d192ffa50d80244afb",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267746334281851/IMG_20251123_223645.jpg?ex=692578c2&is=69242742&hm=829b1eb7f7225568105da7bd020a57aec8d43dacb225e8e5c4f0a8a6d935fec",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745650606171/IMG_20251123_223622.jpg?ex=692578c2&is=69242742&hm=9a6666d6599e93084ac9dd010bcc8bcb8301ca2dd88191f1112ce061da66b7b",
]

PASSWORD = os.getenv("SECRET_CMD_PASSWORD")
ALLOWED_USER_ID = 988470489909432334
WEBHOOK_URL = os.getenv("WEBHOOK_DEP")
NUKE_PASSWORD = os.getenv("NUKE_PASSWORD")
REDEPLOY_PASSWORD = os.getenv("REDEPLOY_PASSWORD")


# -----------------------------------------------------
# Events
# -----------------------------------------------------

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f"Bot conectado, {bot.user}")


# -----------------------------------------------------
# Basicos
# -----------------------------------------------------

@bot.command()
async def hola(ctx):
    await ctx.send(
        "PONG! Btw estoy funcionando y siendo hosteado en el server de ttsmcz RPI5. "
        "(Alternativa a ^ping)"
    )


@bot.command()
async def ping(ctx):
    await ctx.send(
        "¡Hola! Estoy funcionando y siendo hosteado en el server de ttsmcz RPI5. "
        "(Alternativa a ^hola)"
    )


@bot.command()
async def qtfn(ctx):
    author = ctx.author
    await ctx.send(f"Que te fakin nigger {author.mention}")


@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="📖 Goonbot — Lista de Comandos",
        description="Prefijo: `^` para comandos normales. `/` para comandos de barra (slash).",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🔧 Básicos `^`",
        value=(
            "`^hola` / `^ping` — Comprueba si el bot está vivo\n"
            "`^qtfn` — Que te fakin nigger\n"
            "`^help` — Esta ayuda"
        ),
        inline=False
    )

    embed.add_field(
        name="💬 Mensajes `^`",
        value=(
            "`^message_add` — Guarda un mensaje\n"
            "`^message_list` — Lista los mensajes guardados"
        ),
        inline=False
    )

    embed.add_field(
        name="💬 Mensajes `/`",
        value="`/edit_message` — Edita o elimina un mensaje tuyo",
        inline=False
    )

    embed.add_field(
        name="😂 Diversión `^`",
        value=(
            "`^roast [@usuario]` — Insulta a alguien\n"
            "`^rape [@usuario]` — Amenaza a alguien\n"
            "`^rampage @usuario` — Rampage contra un usuario"
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

    await ctx.send(embed=embed)


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