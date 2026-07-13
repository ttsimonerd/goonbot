"""
Guild membership check via the live discord.py bot object — no separate
API call, no `guilds` OAuth scope, no token duplication. Requires the
Server Members privileged intent to be enabled (both in code, already set
via Intents.all() in main.py, and in the Discord Developer Portal).
"""

import discord

from config import GUILD_ID


async def check_membership(bot, discord_id: int) -> tuple[bool, discord.Member | None]:
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        # Bot hasn't finished connecting/caching guilds yet.
        return False, None

    member = guild.get_member(discord_id)
    if member is not None:
        return True, member

    try:
        member = await guild.fetch_member(discord_id)
        return True, member
    except discord.NotFound:
        return False, None
    except discord.HTTPException:
        return False, None
