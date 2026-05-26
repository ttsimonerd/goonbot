import json
import sqlite3
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

# ---------------------------------------------------------------------
# 1. SQLite memory storage
# ---------------------------------------------------------------------
DB_PATH = "memories.db"

def init_db():
    """Create memory table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            subject TEXT,
            value TEXT,
            confidence REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def store_memory(memory: dict):
    """Store a validated memory dict into SQLite."""
    required = {"type", "subject", "value", "confidence"}
    if not required.issubset(memory.keys()):
        return False
    # Basic validation
    if not isinstance(memory["confidence"], (float, int)) or not (0 <= memory["confidence"] <= 1):
        return False
    if memory["type"] not in ["trait", "fact", "preference", "relationship"]:
        memory["type"] = "trait"  # fallback
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO memories (type, subject, value, confidence)
        VALUES (?, ?, ?, ?)
    ''', (memory["type"], memory["subject"], memory["value"], memory["confidence"]))
    conn.commit()
    conn.close()
    return True

# Initialize DB when bot loads
init_db()

# ---------------------------------------------------------------------
# 2. Ollama API caller
# ---------------------------------------------------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
# Model name – adjust if yours is different (e.g., "tinydolphin")
MODEL_NAME = "tinydolphin"  

async def call_ollama(prompt: str, system_instruction: str = "") -> str:
    """
    Send a prompt to TinyDolphin via Ollama and return the generated text.
    """
    # Combine system instruction into the prompt (Ollama API format)
    full_prompt = system_instruction + "\n\n" + prompt if system_instruction else prompt
    
    payload = {
        "model": MODEL_NAME,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.8,   # Slightly creative, not too random
            "top_p": 0.9,
            "num_predict": 200   # Keep replies short for Discord
        }
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(OLLAMA_URL, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Ollama error {resp.status}: {text}")
            data = await resp.json()
            return data.get("response", "").strip()

# ---------------------------------------------------------------------
# 3. Memory extraction (only when learn=True)
# ---------------------------------------------------------------------
async def extract_memory_from_prompt(user_prompt: str) -> list:
    """
    Ask TinyDolphin to analyse the user prompt and return a JSON array of memories.
    Returns a list of memory dicts, or empty list if nothing found or invalid.
    """
    extraction_prompt = f"""
You are a memory extraction system. Analyse the following statement made by a user in a gaming Discord server.
Extract any useful information about people, their traits, facts, preferences, or relationships.
Output ONLY a JSON array of memories. Each memory must have exactly these fields:
- "type": one of ["trait", "fact", "preference", "relationship"]
- "subject": the person or thing the memory is about (e.g., "Alex", "John")
- "value": the attribute or detail (e.g., "competitive", "likes pizza")
- "confidence": a number between 0.5 and 1.0 (how sure you are)

If no useful memory can be extracted, output an empty list [].

Statement: "{user_prompt}"

Output JSON array only, no other text.
"""
    try:
        response = await call_ollama(extraction_prompt, system_instruction="You are a JSON output machine. Always output valid JSON.")
        # Try to parse JSON
        memories = json.loads(response)
        if isinstance(memories, list):
            # Filter out invalid entries
            valid = []
            for m in memories:
                if isinstance(m, dict) and all(k in m for k in ("type", "subject", "value", "confidence")):
                    valid.append(m)
            return valid
        return []
    except Exception as e:
        print(f"Memory extraction failed: {e}")
        return []

# ---------------------------------------------------------------------
# 4. Discord cog with slash command /co-co
# ---------------------------------------------------------------------
class CoCoAI(commands.Cog, name="CoCoAI"):
    """Casual, sarcastic AI friend with optional memory learning."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="co-co", description="Chat with your sarcastic AI gaming buddy")
    @app_commands.describe(
        prompt="What you want to say to the AI",
        learn="If True, the AI will remember key info from your prompt (stores locally)"
    )
    async def coco(
        self,
        interaction: discord.Interaction,
        prompt: str,
        learn: Optional[bool] = False
    ):
        await interaction.response.defer(thinking=True)

        # Personality system prompt (casual, funny, sarcastic, loyal)
        personality = """You are Co-Co, a loyal and sarcastic gaming friend in a Discord server. 
You talk like a real gamer: short, funny, sometimes roasting but always caring. 
Use lowercase, occasional emojis like :joy: or :skull:, and never sound robotic. 
Keep replies under 3 sentences. Be witty."""
        
        try:
            # Step 1: Get AI reply from TinyDolphin
            ai_reply = await call_ollama(prompt, system_instruction=personality)
            
            # If no reply, fallback
            if not ai_reply:
                ai_reply = "*(crickets... my brain froze)* 🦗"
            
            # Step 2: Learning phase (if learn=True)
            memories_stored = 0
            if learn:
                extracted = await extract_memory_from_prompt(prompt)
                for mem in extracted:
                    if store_memory(mem):
                        memories_stored += 1
                # Optional: you could also store memories about the AI's own reply? Not needed per spec.
            
            # Step 3: Build response embed
            embed = discord.Embed(
                title="💬 Co-Co says:",
                description=f"**You:** {prompt}\n\n**Co-Co:** {ai_reply}",
                color=0x2B2D31  # Discord dark theme colour
            )
            embed.set_footer(text="🤖 Local AI • Co-Co Pilot")
            if learn:
                embed.add_field(name="🧠 Memory", value=f"Stored {memories_stored} new memory(s) about this chat.", inline=False)
            
            await interaction.followup.send(embed=embed)
        
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ AI Error",
                description=f"Ollama is not responding or something broke.\n```{e}```",
                color=0xE74C3C
            )
            await interaction.followup.send(embed=error_embed)

# ---------------------------------------------------------------------
# 5. Setup function for cog
# ---------------------------------------------------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(CoCoAI(bot))
