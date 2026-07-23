import os
import aiohttp
import discord
from discord import app_commands, Interaction
from discord.ext import commands

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "OLLAMA_SYSTEM_PROMPT",
    "Eres Lefa, una IA sarcástica, graciosa y vacilona del servidor Discord GoonBot. "
    "Respondes siempre en español castellano con desparpajo y humor, de forma directa, corta y divertida."
)


async def call_ollama(prompt: str, system: str = DEFAULT_SYSTEM_PROMPT) -> str:
    url = f"{OLLAMA_URL.rstrip('/')}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "stream": False
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    return f"⚠️ Error al contactar con Ollama: HTTP {response.status}"
                data = await response.json()
                content = data.get("message", {}).get("content", "").strip()
                return content if content else "*(No recibí respuesta de Ollama)*"
    except Exception as e:
        return f"⚠️ No se pudo conectar con el servidor Ollama local ({OLLAMA_URL}): {e}"


class AITexts(commands.Cog, name="AITexts"):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="lefa", description="Habla con Lefa, la IA local (Qwen2.5 0.5B).")
    @app_commands.describe(prompt="Mensaje o pregunta para la IA")
    async def lefa(
        self,
        interaction: Interaction,
        prompt: str
    ):
        await interaction.response.defer()

        reply = await call_ollama(prompt)
        username = interaction.user.display_name

        embed = discord.Embed(color=0x992D22)
        embed.set_author(name="🥛 Lefa AI")
        embed.add_field(name=f"💬 {username}", value=f"```{prompt[:1000]}```", inline=False)
        embed.add_field(name="🤖 Lefa", value=reply[:1024] if len(reply) <= 1024 else reply[:1021] + "...", inline=False)
        embed.set_footer(text=f"Model: {OLLAMA_MODEL} • Local Ollama")

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AITexts(bot))
