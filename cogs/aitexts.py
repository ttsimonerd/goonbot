import os
import aiohttp
import base64
import discord
from discord import app_commands, Interaction
from discord.ext import commands

OPENROUTER_API_KEY = os.getenv("OPENROUTER_APIKEY")
AI_TEXT_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"


async def generate_ai_reply(sender: str, receiver: str, message: str) -> str:
    """Calls OpenRouter to generate a funny AI text message reply."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        f"Eres {receiver}, un usuario de Discord con personalidad cómica y vacilón. "
        f"Alguien llamado {sender} te acaba de enviar un mensaje de texto. "
        f"Responde al mensaje de forma corta, divertida y natural como si fuera una conversación de WhatsApp/SMS. "
        f"Responde solo con el texto del mensaje de vuelta, nada más. Máximo 2 frases."
    )

    payload = {
        "model": AI_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Mensaje recibido: \"{message}\""},
        ],
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                return "*(sin señal... 📵)*"
            data = await response.json()
            return data["choices"][0]["message"]["content"].strip()


class AITexts(commands.Cog, name="AITexts"):
    """Comando de mensajes de texto simulados con IA."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="text", description="Envía un texto a alguien y la IA responde como si fuera esa persona.")
    @app_commands.describe(
        user="A quién le envías el mensaje",
        message="El mensaje que quieres enviar"
    )
    async def text(self, interaction: Interaction, user: discord.Member, message: str):
        await interaction.response.defer()

        sender_name = interaction.user.display_name
        receiver_name = user.display_name

        ai_reply = await generate_ai_reply(sender_name, receiver_name, message)

        # Build a phone-bubble style embed
        embed = discord.Embed(color=0x1e1e2e)
        embed.set_author(
            name=f"📱 Conversación entre {sender_name} y {receiver_name}",
        )

        # Sender bubble
        embed.add_field(
            name=f"💬 {sender_name}",
            value=f"```{message}```",
            inline=False
        )

        # AI reply bubble
        embed.add_field(
            name=f"💬 {receiver_name}",
            value=f"```{ai_reply}```",
            inline=False
        )

        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text="📶 goonbot SMS • IA powered")

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AITexts(bot))
