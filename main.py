from keep_alive import keep_alive
import os
import discord # type: ignore
from discord.ext import commands # type: ignore
from discord import app_commands # type: ignore
from discord import ui  # Added missing import for ui components
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
DB_FILE = "messages_db.txt"
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

# -----------------------------
# Data Base
# -----------------------------

def cargar_mensajes():
    if not os.path.exists(DB_FILE) or os.path.getsize(DB_FILE) == 0:
        return []
    with open(DB_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            f.seek(0)
            lines = f.readlines()
            mensajes = [{
                "content": line.strip(),
                "author_id": None
            } for line in lines if line.strip()]
            guardar_mensajes(mensajes)
            return mensajes


def guardar_mensajes(mensajes):
    with open(DB_FILE, "w") as f:
        json.dump(mensajes, f, indent=4)


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
    try:
        await bot.tree.sync()
        print("Sync Succes!")
    except Exception as e:
        print("Sync error:", e)

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

# -----------------------------
# Cog1 - Mensajes
# -----------------------------
class Mensajes(commands.Cog, name="Mensajes"):
    """Comandos para manejar mensajes guardados"""

    def __init__(self, bot):
        self.bot = bot

    # Add message
    @commands.command(name="message_add")
    async def message_add(self, ctx, *, mensaje: str):
        mensajes = cargar_mensajes()
        mensajes.append({"content": mensaje, "author_id": ctx.author.id})
        guardar_mensajes(mensajes)
        await ctx.send(f"✅ Mensaje añadido. Total mensajes: {len(mensajes)}")

    # List messages
    @commands.command(name="message_list")
    async def message_list(self, ctx):
        mensajes = cargar_mensajes()
        if not mensajes:
            await ctx.send("No hay mensajes guardados.")
            return
        listado = "\n".join(
            [f"{i+1}. {m['content']}" for i, m in enumerate(mensajes)])
        await ctx.send(f"📄 Mensajes guardados:\n{listado}")

    # Edit/Del messages (Slash Comm)
    @app_commands.command(
        name="edit_message",
        description="Editar o eliminar un mensaje que hayas añadido",
    )
    @app_commands.describe(
        index="Índice del mensaje a editar/eliminar (1, 2, 3, ...)",
        new_content="Nuevo contenido del mensaje",
        delete="Eliminar el mensaje en lugar de editarlo")
    async def edit_message(self,
                           interaction: discord.Interaction,
                           index: int,
                           new_content: str | None = None,
                           delete: bool = False):
        mensajes = cargar_mensajes()

        if index < 1 or index > len(mensajes):
            await interaction.response.send_message("❌ Índice inválido.",
                                                    ephemeral=True)
            return

        mensaje = mensajes[index - 1]

        # Validar propietario
        if mensaje["author_id"] is not None and mensaje[
                "author_id"] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Solo puedes editar/eliminar tus propios mensajes.",
                ephemeral=True)
            return

        if delete:
            mensajes.pop(index - 1)
            guardar_mensajes(mensajes)
            await interaction.response.send_message(
                "✅ Mensaje eliminado correctamente.", ephemeral=True)
        else:
            if not new_content:
                await interaction.response.send_message(
                    "❌ Debes proporcionar un nuevo contenido para editar.",
                    ephemeral=True)
                return
            mensaje["content"] = new_content
            mensaje["author_id"] = interaction.user.id
            guardar_mensajes(mensajes)
            await interaction.response.send_message(
                "✅ Mensaje editado correctamente.", ephemeral=True)

# ---------------------------------------------
#   COG PRINCIPAL
# ---------------------------------------------
class SecretCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="admindashboard",
        description="Need autorization."
    )
    async def secret(self, interaction: discord.Interaction):  # Fixed type hint

        # Solo tú puedes usarlo
        if interaction.user.id != ALLOWED_USER_ID:
            await interaction.response.send_message(
                "Not autorized.",
                ephemeral=True
            )
            return

        result = roll_with_limit()

        await interaction.response.send_message(
            f"Resultado: {result}",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(SecretCommand(bot))


# -----------------------------
# Cog1 Setup
# -----------------------------
async def setup_cogs1():
    await bot.add_cog(Mensajes(bot))


asyncio.run(setup_cogs1())


# -----------------------------
# Cog2 - Fun
# -----------------------------
class Fun(commands.Cog, name="Fun"):
    """Comandos de diversión, etc..."""

    def __init__(self, bot):
        self.bot = bot

    #___________ROAST______________
    @commands.command(name="roast")
    async def roast(self, ctx, user: discord.Member = None):  # type: ignore

        roasts = [
            "Fatass Nigger", "Stupid Monkey", "Fucking Idiot", "Stupid Nigga",
            "Multiplicate por 0", "Eres un pedazo de payo",
            "Más payo que un mono",
            "Más payo que los sandwiches de triangulos", "Butanero"
        ]

        target = user or ctx.author
        roast = random.choice(roasts)

        await ctx.send(f"😂 {target.mention}, {roast}")

    #___________RAPE______________
    @commands.command(name="rape")
    async def rape(self, ctx, user: discord.Member = None):  # type: ignore

        rapes = [
            "Imma Rape You Nigga", "Ur gonna get raped", "Vas a rape"
        ]

        target = user or ctx.author
        rape = random.choice(rapes)

        await ctx.send(f"🥶 {target.mention}, {rape} 💔🎋✌😂")

    # ___________RAMPAGE_____________
    @commands.command(name="rampage")
    async def rampage(self, ctx, target: discord.Member = None):
        """
        RAMPAGE
        """

        if target is None:
            await ctx.send("Debes mencionar un usuario.")
            return

        # Embed inicial
        embed = discord.Embed(
            title="Rampage",
            description=f"RAMPGAE {target.mention}...\nRAMPAGE...",
            color=discord.Color.red()
        )
        msg = await ctx.send(embed=embed)

        # Reacciones aleatorias
        reaction_pool = ["🔥", "💀", "😈", "🤖", "⚡", "🧨"]

        # Buscar últimos mensajes del target
        mensajes_target = []
        async for mensaje in ctx.channel.history(limit=200):
            if mensaje.author.id == target.id:
                mensajes_target.append(mensaje)
            if len(mensajes_target) == 20:
                break

        # Añadir reacciones
        for mensaje in mensajes_target:
            try:
                await mensaje.add_reaction(random.choice(reaction_pool))
            except:
                pass

        ataques = [
            "{user} NIGGA",
            "{user} STUPID NIGGER",
            "{user} RAMPAGED NIGGER",
        ]

        for ataque in ataques:
            await ctx.send(ataque.replace("{user}", target.mention))

        gifs = [
            "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExZTM2cGRvbDBjaWE1cHJudXVmdTZodmpjd3JybjI4MXowczJkMWVkaSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/fl0B5TLMTYLPvNervP/giphy.gif",
            "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExcHN2ZW9lc2doc2xndGFzNHpzNnF4ZXQyZjl0Y3F1MWRwNnV5cndpdyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/wrmVCNbpOyqgJ9zQTn/giphy.gif",
        ]

        await ctx.send(random.choice(gifs))

# -----------------------------
# Cog2 Setup
# -----------------------------
async def setup_cogs2():
    await bot.add_cog(Fun(bot))


asyncio.run(setup_cogs2())

# Setup SecretCommand
asyncio.run(setup(bot))  # Added call to cog

# -----------------------------
# Bot main
# -----------------------------
token = os.getenv("DISCORD_TOKEN")
bot.run(token)  # type: ignore
