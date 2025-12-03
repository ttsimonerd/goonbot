from keep_alive import keep_alive
import os
import discord # type: ignore
from discord.ext import commands # type: ignore
from discord import app_commands # type: ignore
import json
import asyncio
import random
from probabilities import roll_with_limit

keep_alive()

intents = discord.Intents.all()
intents.message_content = True


# -----------------------------------------------------
# Prefix, variables & things...
# -----------------------------------------------------
bot = commands.Bot(command_prefix="^", intents=intents)
DB_FILE = "messages_db.txt"
IMAGE_URLS = [
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745012944956/IMG_20251123_223528.jpg?ex=692578c2&is=69242742&hm=4b47769727c175f0c1af171968e04cbe134e6c494a87811b7d6c1044d49b7e2e&",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745344426136/IMG_20251123_223600.jpg?ex=692578c2&is=69242742&hm=2abd81e14fc934758414968a69baf6f4eca971f094adabc7a9cfc37b44da663b&",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745986285749/IMG_20251123_223634.jpg?ex=692578c2&is=69242742&hm=115629a925ba57951db272b46001940669e6d2928b077d192ffa50d80244afba&",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267746334281851/IMG_20251123_223645.jpg?ex=692578c2&is=69242742&hm=829b1eb7f7225568105da7bd020a57aec8d43dacb225e8e5c4f0a8a6d935fecf&", 
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745650606171/IMG_20251123_223622.jpg?ex=692578c2&is=69242742&hm=9a6666d6599e93084ac9dd010bcc8bcb8301ca2dd88191f1112ce061da72f644&", 
]

PASSWORD = os.getenv("SECRET_CMD_PASSWORD")
ALLOWED_USER_ID = "988470489909432334"

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
async def on_ready():
    await bot.tree.sync()
    print(f"Bot conectado como {bot.user}")
    try:
        await bot.tree.sync()
        print("Sync Succes!")
    except Exception as e:
        print("Sync error:", e)

@bot.event
async def on_message(message):
    # Ignore bot
    if message.author == bot.user:
        return
    
    await bot.process_commands(message)
    
    # Updated chance for rr event, now its 1%
    if random.random() < 0.01:
        text_channels = [channel for channel in message.guild.channels if isinstance(channel, discord.TextChannel)]
        if not text_channels:
            return
        random_channel = random.choice(text_channels)
        try:
            recent_messages = await random_channel.history(limit=100).flatten()
            
            if not recent_messages:
                return
            random_msg = random.choice(recent_messages)
            
            random_image_url = random.choice(IMAGE_URLS)
            
            embed = discord.Embed(
                title="GREEN COMBO",
                description="Green... 🟩",
                color=discord.Color.green()
            )
            embed.set_image(url=random_image_url)
            
            await random_msg.reply(embed=embed)
        
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"Error in rr: {e}")

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
async def qtfn(self, ctx):
    self = ctx.author
    await ctx.send(
        f"Que te fakin nigger {self.mention}"
    )

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
                           new_content: str = " ",
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
# ----------------------
# Cog - Inv
# ----------------------


class PasswordModal(ui.Modal, title="Autenticación requerida"):
    password = ui.TextInput(
        label="Introduce la contraseña",
        placeholder="Escribe aquí...",
        required=True,
        min_length=1
    )

    async def on_submit(self, interaction: Interaction):
        user_input = str(self.password.value).strip()

        if user_input != PASSWORD:
            await interaction.response.send_message(
                "Contraseña incorrecta.",
                ephemeral=True
            )
            return

        result = roll_with_limit()

        await interaction.response.send_message(
            f"Resultado: {result}",
            ephemeral=True
        )


# ---------------------------------------------
#   COG PRINCIPAL
# ---------------------------------------------
class SecretCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="secreto",
        description="Comando reservado únicamente para el administrador autorizado."
    )
    async def secret(self, interaction: Interaction):

        # Solo tú puedes usarlo
        if interaction.user.id != ALLOWED_USER_ID:
            await interaction.response.send_message(
                "No tienes permiso para usar este comando.",
                ephemeral=True
            )
            return

        # Abrir modal de contraseña
        modal = PasswordModal()
        await interaction.response.send_modal(modal)


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
            "NIGGA",
            "STUPID NIGGER",
            "RAMPAGED NIGGER",
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
# -----------------------------
# Bot main
# -----------------------------
token = os.getenv("DISCORD_TOKEN")
bot.run(token)  # type: ignore
