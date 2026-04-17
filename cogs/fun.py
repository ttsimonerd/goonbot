import discord
import random
from discord.ext import commands

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

async def setup(bot):
    await bot.add_cog(Fun(bot))
