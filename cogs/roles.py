"""Roles & announcements for rare RNG drops.

Called by the RNG engine (and the inventory sell flow) whenever a player
drops — or stops owning — an item from a role tier (Goon Master / Seguito
del GoonBot, i.e. rarer than 1 in 100,000).

The announcement channel is configured with /settings rng_channel and the
roles with /settings rng_role.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

import db
from config import RNG_ROLE_TIERS

logger = logging.getLogger(__name__)

# Tier name -> settings key holding the configured role id.
_ROLE_SETTING_KEYS = {
    "Goon Master": "rng_role_goon_master_id",
    "Seguito del GoonBot": "rng_role_seguito_id",
}


class Roles(commands.Cog, name="Roles"):
    """Anuncios y roles por drops raros del gacha RNG."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def on_rare_drop(self, guild: discord.Guild, user_id: int, item: dict) -> None:
        """Announce a Goon Master+ drop and grant its role."""
        settings = await db.get_settings(guild.id)

        await self._post_announcement(guild, settings, user_id, item)
        await self._grant_role(guild, settings, user_id, item)

    async def on_sold(self, guild: discord.Guild, user_id: int, item: dict) -> None:
        """Remove the tier role when the player sells their last such item."""
        if item["rarity_tier"] not in RNG_ROLE_TIERS:
            return
        inventory = await db.rng_get_inventory(guild.id, user_id)
        still_owns = any(
            x["name"] == item["name"] and x["quantity"] > 0 for x in inventory
        )
        if still_owns:
            return

        settings = await db.get_settings(guild.id)
        role_id = settings.get(_ROLE_SETTING_KEYS[item["rarity_tier"]])
        if not role_id:
            return
        member = guild.get_member(user_id)
        role = guild.get_role(role_id)
        if member is None or role is None or role not in member.roles:
            return
        try:
            await member.remove_roles(role, reason="RNG item sold")
            logger.info("Removed RNG role %s from %s", role.name, member)
        except discord.HTTPException as e:
            logger.warning("Couldn't remove RNG role: %s", e)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _post_announcement(
        self,
        guild: discord.Guild,
        settings: dict,
        user_id: int,
        item: dict,
    ) -> None:
        channel_id = settings.get("rng_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return

        embed = discord.Embed(
            title="🔥 ¡DROP MÍIIITICO! 🔥",
            description=(
                f"{item['icon_emoji']} **{item['name']}**\n"
                f"{item['description']}"
            ),
            color=discord.Color.gold(),
        )
        embed.add_field(name="🎚️ Tier", value=item["rarity_tier"], inline=True)
        embed.add_field(name="👤 Jugador", value=f"<@{user_id}>", inline=True)
        embed.add_field(name="Probabilidad", value="1 en 100.000 o más raro", inline=False)
        embed.set_footer(text="GoonBot RNG")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            logger.warning("Couldn't post RNG announcement: %s", e)

    async def _grant_role(
        self,
        guild: discord.Guild,
        settings: dict,
        user_id: int,
        item: dict,
    ) -> None:
        role_id = settings.get(_ROLE_SETTING_KEYS.get(item["rarity_tier"], ""))
        if not role_id:
            return
        member = guild.get_member(user_id)
        role = guild.get_role(role_id)
        if member is None or role is None:
            return
        if role in member.roles:
            return
        try:
            await member.add_roles(role, reason="RNG drop")
            logger.info("Granted RNG role %s to %s", role.name, member)
        except discord.HTTPException as e:
            logger.warning("Couldn't grant RNG role: %s", e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roles(bot))
