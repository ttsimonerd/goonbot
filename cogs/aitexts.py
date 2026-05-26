import os
import sqlite3
import aiohttp
import discord
from discord import app_commands, Interaction
from discord.ext import commands

OPENROUTER_API_KEY = os.getenv("OPENROUTER_APIKEY")
AI_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
DB_FILE = "clanker_memory.db"

SYSTEM_PROMPT = """
Eres 'Co-Co Pilot', una IA con personalidad de colega vacilón del grupo. Hablas español castellano con mucho desparpajo.
Eres gracioso, haces roasts, usas palabrotas cuando viene al caso, y te adaptas al rollo de cada persona según lo que sabes de ellos.
Puedes ser sarcástico, irónico, y a veces hasta un poco cabrón, pero siempre en plan de broma entre colegas.
Recuerdas todo lo que la gente te ha dicho antes y lo usas para vacílarles.
Respuestas cortas y directas, como en un chat. Máximo 3-4 frases salvo que te pidan algo largo.
Si no sabes algo, preguntalo!
"""

# ---------------------
# Database
# ---------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT,
            user_id TEXT,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT,
            user_id TEXT,
            fact TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_history(guild_id: str, user_id: str, limit: int = 20) -> list:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT role, content FROM messages
        WHERE guild_id = ? AND user_id = ?
        ORDER BY timestamp DESC LIMIT ?
    """, (guild_id, user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"role": r, "content": c} for r, c in reversed(rows)]

def save_message(guild_id: str, user_id: str, role: str, content: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO messages (guild_id, user_id, role, content)
        VALUES (?, ?, ?, ?)
    """, (guild_id, user_id, role, content))
    conn.commit()
    conn.close()

def get_user_facts(guild_id: str, user_id: str) -> str:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT fact FROM user_facts
        WHERE guild_id = ? AND user_id = ?
        ORDER BY timestamp DESC LIMIT 10
    """, (guild_id, user_id))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return ""
    return "Lo que sé de esta persona: " + " | ".join(r[0] for r in rows)

def save_fact(guild_id: str, user_id: str, fact: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO user_facts (guild_id, user_id, fact)
        VALUES (?, ?, ?)
    """, (guild_id, user_id, fact))
    conn.commit()
    conn.close()

def delete_user_memory(guild_id: str, user_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    c.execute("DELETE FROM user_facts WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    conn.commit()
    conn.close()

# ---------------------
# AI Call
# ---------------------
async def call_clanker(guild_id: str, user_id: str, username: str, message: str) -> str:
    history = get_history(guild_id, user_id)
    facts = get_user_facts(guild_id, user_id)

    system = SYSTEM_PROMPT
    if facts:
        system += f"\n\n{facts}"

    messages = [{"role": "system", "content": system}]
    messages += history
    messages.append({"role": "user", "content": f"{username}: {message}"})

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "max_tokens": 500,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                return "*(no estoy conectado, nigga... 📵)*"
            data = await response.json()
            reply = data["choices"][0]["message"]["content"].strip()

    save_message(guild_id, user_id, "user", f"{username}: {message}")
    save_message(guild_id, user_id, "assistant", reply)

    return reply

# ---------------------
# Cog
# ---------------------
class AITexts(commands.Cog, name="AITexts"):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_db()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Learn facts from chat messages automatically."""
        if message.author.bot:
            return
        if not message.guild:
            return
        if len(message.content) < 10:
            return

        # Save every message as a fact to learn from
        save_fact(
            str(message.guild.id),
            str(message.author.id),
            f"{message.author.display_name} dijo: {message.content[:200]}"
        )

    @app_commands.command(name="clanker", description="Habla con el Co-Co Pilot!")
    @app_commands.describe(
        message="...",
        temperature="(0.0 - 2.0, default 1.0)"
    )
    async def clanker(
        self,
        interaction: Interaction,
        message: str,
        temperature: float = 1.0
    ):
        if not (0.0 <= temperature <= 2.0):
            await interaction.response.send_message("❌ temp must be 0.0 - 2.0 my negga", ephemeral=True)
            return

        await interaction.response.defer()

        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        username = interaction.user.display_name

        reply = await call_clanker(guild_id, user_id, username, message)

        embed = discord.Embed(color=0x1e1e2e)
        embed.set_author(name="🤖 Co-Co Pilot")
        embed.add_field(name=f"💬 {username}", value=f"```{message[:1000]}```", inline=False)
        embed.add_field(name="🤖 Co-Co Pilot", value=reply[:1024], inline=False)
        embed.set_footer(text=f"Model: custom | Temp: {temperature}")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="forget", description="[ADMIN] Borra la memoria del Co-Co Pilot sobre un usuario.")
    @app_commands.describe(user="Usuario cuya memoria borrar")
    @app_commands.default_permissions(administrator=True)
    async def forget(self, interaction: Interaction, user: discord.Member):
        delete_user_memory(str(interaction.guild_id), str(user.id))
        await interaction.response.send_message(
            f"🗑️ Memoria de {user.mention} borrada.",
            ephemeral=True
        )

    @app_commands.command(name="text", description="Envía un texto a alguien y la IA responde como si fuese esa persona.")
    @app_commands.describe(
        user="...",
        message="..."
    )
    async def text(self, interaction: Interaction, user: discord.Member, message: str):
        await interaction.response.defer()

        sender_name = interaction.user.display_name
        receiver_name = user.display_name

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": AI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"Eres {receiver_name}, un usuario de Discord con personalidad cómica y vacilona. "
                        f"Alguien llamado {sender_name} te acaba de enviar un mensaje. "
                        f"Responde de forma corta, divertida y natural como en WhatsApp. Máximo 2 frases."
                    )
                },
                {"role": "user", "content": f"Mensaje recibido: \"{message}\""}
            ],
            "max_tokens": 200,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    ai_reply = "*(no tengo señal nigga... 📵)*"
                else:
                    data = await response.json()
                    ai_reply = data["choices"][0]["message"]["content"].strip()

        embed = discord.Embed(color=0x1e1e2e)
        embed.set_author(name=f"📱 Conversación entre {sender_name} y {receiver_name}")
        embed.add_field(name=f"💬 {sender_name}", value=f"```{message[:1000]}```", inline=False)
        embed.add_field(name=f"💬 {receiver_name}", value=f"```{ai_reply[:1000]}```", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text="📶 goonbot bearer • powered by Co-Co Pilot AI • Made by ttsmcz")

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AITexts(bot))
