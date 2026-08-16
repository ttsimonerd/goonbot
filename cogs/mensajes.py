import json
import os

import discord
from discord import app_commands
from discord.ext import commands

import db

LEGACY_DB_FILE = "messages_db.txt"


class Mensajes(commands.Cog, name="Mensajes"):
    """Comandos para manejar mensajes guardados (almacenados en SQLite)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Migra los mensajes del antiguo archivo plano a la base de datos."""
        if not os.path.exists(LEGACY_DB_FILE):
            return

        try:
            with open(LEGACY_DB_FILE, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    items = [
                        (int(m.get("author_id") or 0), m["content"])
                        for m in data
                    ]
                except json.JSONDecodeError:
                    f.seek(0)
                    items = [
                        (0, line.strip())
                        for line in f
                        if line.strip()
                    ]
        except Exception:
            # Migration failed — leave the file untouched for a future attempt.
            return

        for author_id, content in items:
            await db.add_saved_message(author_id, content)

        os.remove(LEGACY_DB_FILE)

    # Add message
    @app_commands.command(name="message_add", description="Guarda un mensaje")
    @app_commands.describe(mensaje="El mensaje a guardar")
    async def message_add(self, interaction: discord.Interaction, mensaje: str) -> None:
        """Guarda un mensaje en la base de datos."""
        message_id = await db.add_saved_message(interaction.user.id, mensaje)
        await interaction.response.send_message(f"✅ Mensaje añadido (ID #{message_id}).")

    # List messages
    @app_commands.command(name="message_list", description="Lista los mensajes guardados")
    async def message_list(self, interaction: discord.Interaction) -> None:
        """Lista los mensajes guardados."""
        mensajes = await db.get_saved_messages()
        if not mensajes:
            await interaction.response.send_message("No hay mensajes guardados.")
            return
        listado = "\n".join(f"**#{m['id']}.** {m['content']}" for m in mensajes)
        await interaction.response.send_message(f"📄 Mensajes guardados:\n{listado}")

    # Edit/Del messages
    @app_commands.command(
        name="edit_message",
        description="Editar o eliminar un mensaje que hayas añadido",
    )
    @app_commands.describe(
        message_id="ID del mensaje a editar/eliminar (ver /message_list)",
        new_content="Nuevo contenido del mensaje",
        delete="Eliminar el mensaje en lugar de editarlo")
    async def edit_message(
        self,
        interaction: discord.Interaction,
        message_id: int,
        new_content: str | None = None,
        delete: bool = False,
    ) -> None:
        """Edita o elimina un mensaje guardado por el propio usuario."""
        mensaje = await db.get_saved_message(message_id)
        if mensaje is None:
            await interaction.response.send_message("❌ ID inválido.", ephemeral=True)
            return

        # Validar propietario
        if mensaje["author_id"] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Solo puedes editar/eliminar tus propios mensajes.",
                ephemeral=True,
            )
            return

        if delete:
            await db.delete_saved_message(message_id)
            await interaction.response.send_message(
                "✅ Mensaje eliminado correctamente.", ephemeral=True
            )
        else:
            if not new_content:
                await interaction.response.send_message(
                    "❌ Debes proporcionar un nuevo contenido para editar.",
                    ephemeral=True,
                )
                return
            await db.update_saved_message(message_id, new_content)
            await interaction.response.send_message(
                "✅ Mensaje editado correctamente.", ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Mensajes(bot))
