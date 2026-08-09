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
            "Imma Rape You Nih", "Ur gonna get raped", "Vas a rape"
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
            except Exception:
                pass

        ataques = [
            "{user} Dise bro bro bro",
            "{user} Lol :sob:",
            "{user} Sonbrero :sob:",
        ]

        for ataque in ataques:
            await ctx.send(ataque.replace("{user}", target.mention))

        gifs = [
            "https://klipy.com/gifs/tusmu-pez",
            "https://klipy.com/gifs/son-im-crine-8",
            "https://klipy.com/gifs/yuji-11",
            "https://klipy.com/gifs/reinteller-meme",
            "https://klipy.com/gifs/crine-im-crine",
            "https://klipy.com/gifs/goon-pigeon",
            "https://klipy.com/gifs/fat-ayanokoji",
            "https://klipy.com/gifs/companion-meme-2",
            "https://klipy.com/gifs/descendant-meme"
        ]

        await ctx.send(random.choice(gifs))

async def setup(bot):
    await bot.add_cog(Fun(bot))
