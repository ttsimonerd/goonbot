from keep_alive import keep_alive
import os
import discord
from discord.ext import commands
from discord import app_commands
import json
import asyncio
import random

keep_alive()

intents = discord.Intents.all()
intents.message_content = True

# Prefix, variables & things...
bot = commands.Bot(command_prefix="^", intents=intents)
DB_FILE = "messages_db.txt"

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
