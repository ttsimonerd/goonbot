import discord
import random
from discord import app_commands
from discord.ext import commands

class Fun(commands.Cog, name="Fun"):
    """Comandos de diversión, etc..."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    #___________ROAST______________
    @app_commands.command(name="roast", description="Insulta a alguien (JK)")
    @app_commands.describe(user="Usuario objetivo (opcional)")
    async def roast(self, interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        """Insulta a un usuario (o al autor)."""

        roasts = [
            "Fatass Nigger", "Stupid Monkey", "Fucking Idiot", "Stupid Nigga",
            "Multiplicate por 0", "Eres un pedazo de payo",
            "Más payo que un mono",
            "Más payo que los sandwiches de triangulos", "Butanero"
        ]

        target = user or interaction.user
        roast = random.choice(roasts)

        await interaction.response.send_message(f"😂 {target.mention}, {roast}")

    #___________GRAPE______________
    @app_commands.command(name="grape", description="Amenaza a alguien (JK)")
    @app_commands.describe(user="Usuario objetivo (opcional)")
    async def grape(self, interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        """Amenaza a un usuario (o al autor)."""

        grapes = [
            "Imma Rape You Nih", "Ur gonna get raped", "Vas a rape"
        ]

        target = user or interaction.user
        grape = random.choice(grapes)

        await interaction.response.send_message(
            f"🥶 {target.mention}, {grape} 💔🎋✌😂\n"
        )

    # ___________RAMPAGE_____________
    @app_commands.command(name="rampage", description="RAMPAGE contra un usuario")
    @app_commands.describe(target="Usuario objetivo")
    async def rampage(self, interaction: discord.Interaction, target: discord.Member) -> None:
        """Rampage contra un usuario: reacciones, mensajes y un gif."""
        await interaction.response.defer()

        # Embed inicial
        embed = discord.Embed(
            title="Rampage",
            description=f"RAMPGAE {target.mention}...\nRAMPAGE...",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

        # Reacciones aleatorias
        reaction_pool = ["🔥", "💀", "😈", "🤖", "⚡", "🧨"]

        # Buscar últimos mensajes del target
        mensajes_target = []
        channel = interaction.channel
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            async for mensaje in channel.history(limit=200):
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
            await interaction.followup.send(ataque.replace("{user}", target.mention))

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

        await interaction.followup.send(random.choice(gifs))

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fun(bot))
