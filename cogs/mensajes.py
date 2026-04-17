import os
import json
import discord
from discord.ext import commands
from discord import app_commands

DB_FILE = "messages_db.txt"

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

async def setup(bot):
    await bot.add_cog(Mensajes(bot))
