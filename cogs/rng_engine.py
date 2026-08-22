"""Weighted RNG engine — the GoonBot gacha (Sol's RNG-style).

Handles the weighted drop roll (with pity + luck multipliers + global event
hooks), the manual /roll command, the consumable-triggered auto-roll loop,
the token shop, and the admin /rng event commands.

The inventory UI lives in cogs/inventory_ui.py and the rare-drop roles and
announcements in cogs/roles.py; this cog is the source of truth for roll
logic and is looked up from those cogs when they need it.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

import db
from config import (
    GOONBOT_TOKEN_EMOJI,
    RNG_AUTO_COOLDOWN,
    RNG_AUTO_DURATION,
    RNG_EVENTS_SCHEDULE,
    RNG_MANUAL_COOLDOWN,
    RNG_PITY_THRESHOLD,
    RNG_ROLE_TIERS,
    RNG_TIERS,
    RNG_TOKENS_MAX,
    RNG_TOKENS_MIN,
)

logger = logging.getLogger(__name__)

TIER_NAMES = [t[0] for t in RNG_TIERS]
TIER_ODDS = {t[0]: t[1] for t in RNG_TIERS}

# Per-tier embed colors, indexed by tier position.
_TIER_COLORS = [
    discord.Color.light_gray(),
    discord.Color.green(),
    discord.Color.blue(),
    discord.Color.purple(),
    discord.Color.red(),
    discord.Color.dark_red(),
    discord.Color.gold(),
    discord.Color.from_str("#ff00ff"),
]


def now_iso() -> str:
    return datetime.datetime.utcnow().isoformat()


def tier_index(tier: str | None) -> int:
    """Position of a tier in the rarity order (0 = Folk)."""
    if tier in TIER_NAMES:
        return TIER_NAMES.index(tier)
    return -1


def tier_color(tier: str) -> discord.Color:
    idx = tier_index(tier)
    return _TIER_COLORS[idx] if 0 <= idx < len(_TIER_COLORS) else discord.Color.dark_gray()


def _tier_above(tier: str | None) -> str | None:
    """One tier above the given tier, or None if already at the top."""
    idx = tier_index(tier)
    if idx < 0 or idx >= len(TIER_NAMES) - 1:
        return None
    return TIER_NAMES[idx + 1]


def _luck_bar(pity: int, threshold: int = RNG_PITY_THRESHOLD) -> str:
    filled = min(10, int(pity / threshold * 10)) if threshold else 0
    return "▓" * filled + "░" * (10 - filled)


def _roll_embed(user: discord.User, result: dict) -> discord.Embed:
    """Embed shown after a roll (manual, auto unlock, or Re-Goon)."""
    item = result["item"]
    embed = discord.Embed(
        title=f"{item['icon_emoji']} **{item['name']}**",
        description=item["description"],
        color=tier_color(result["tier"]),
    )
    embed.add_field(name="🎚️ Tier", value=result["tier"], inline=True)
    state = "✨ ¡NUEVO!" if result["is_new"] else "🔁 Duplicado"
    embed.add_field(name="Estado", value=state, inline=True)

    tokens = f"{GOONBOT_TOKEN_EMOJI} **+{result['tokens_earned']}**"
    if result["extra_tokens"]:
        tokens += f" (+{result['extra_tokens']} duplicado)"
    embed.add_field(name="Tokens", value=tokens, inline=True)

    embed.add_field(
        name="Pity",
        value=f"`{_luck_bar(result['pity'])}` {result['pity']}/{RNG_PITY_THRESHOLD}",
        inline=False,
    )

    sources = result.get("sources") or []
    luck_line = f"x{result['luck']:.2f}"
    if sources:
        luck_line += f" ({', '.join(sources[:4])})"
    embed.add_field(name="Suerte", value=luck_line, inline=False)

    if result["guaranteed"]:
        embed.add_field(
            name="🎯 Pity garantizado",
            value=f"¡Drop garantizado: **{result['tier']}**!",
            inline=False,
        )
    embed.set_footer(text=f"{user.display_name} · Roll #{result['total_rolls']}")
    return embed


def _auto_summary_embed(user: discord.User, stats: dict, completed: bool) -> discord.Embed:
    """Summary posted when an auto-roll session ends (or is stopped)."""
    title = "✅ Auto-roll completado" if completed else "🛑 Auto-roll detenido"
    embed = discord.Embed(
        title=title,
        description=f"{user.mention} resumen de la sesión:",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="🎲 Rolls", value=str(stats["rolls"]), inline=True)
    embed.add_field(name="✨ Nuevos desbloqueos", value=str(stats["unlocks"]), inline=True)
    embed.add_field(
        name="Tokens",
        value=f"{GOONBOT_TOKEN_EMOJI} {stats['tokens']}",
        inline=True,
    )
    embed.add_field(name="🏆 Mejor tier", value=stats["best"] or "—", inline=False)
    return embed


class Rng(commands.Cog, name="Rng"):
    """Sistema gacha GoonBot (rolls, pity, tienda, eventos)."""

    shop_group = app_commands.Group(name="shop", description="Tienda de GoonBot Tokens")
    rng_group = app_commands.Group(
        name="rng",
        description="[ADMIN] Gestión de eventos RNG",
        default_permissions=discord.Permissions(administrator=True),
    )
    event_group = app_commands.Group(name="event", description="Eventos globales de suerte", parent=rng_group)

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # (guild_id, user_id) -> asyncio.Task of the running auto-roll loop.
        self._auto: dict[tuple[int, int], asyncio.Task] = {}

    async def cog_load(self) -> None:
        """Arranca el bucle de eventos globales al cargar el cog."""
        self.bot.create_background_task(self._event_loop())

    # ------------------------------------------------------------------
    # Background: global events + buff cleanup
    # ------------------------------------------------------------------

    async def _event_loop(self) -> None:
        await self.bot.wait_until_ready()
        while True:
            try:
                await db.rng_cleanup_events()
                await db.rng_cleanup_expired_buffs()
                await self._apply_scheduled_events()
            except Exception:
                logger.exception("RNG event loop error")
            await asyncio.sleep(60)

    async def _apply_scheduled_events(self) -> None:
        """Activate recurring events from config.RNG_EVENTS_SCHEDULE."""
        for entry in RNG_EVENTS_SCHEDULE:
            try:
                name = entry["name"]
                multiplier = entry["multiplier"]
                weekday = entry.get("weekday")
                start_hour = entry["start_hour"]
                end_hour = entry["end_hour"]
            except KeyError:
                logger.warning("Skipping malformed RNG event entry: %s", entry)
                continue

            now = datetime.datetime.utcnow()
            if weekday is not None and now.weekday() != weekday:
                continue
            if not (start_hour <= now.hour < end_hour):
                continue

            active = await db.rng_active_events()
            if any(e["name"] == name for e in active):
                continue

            if end_hour >= 24:
                # All-day window: event ends at midnight (start of next day).
                ends_at = now.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) + datetime.timedelta(days=1)
            else:
                ends_at = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
            await db.rng_start_event(name, multiplier, ends_at.isoformat())
            logger.info("RNG scheduled event started: %s (x%s)", name, multiplier)

    # ------------------------------------------------------------------
    # Core roll logic
    # ------------------------------------------------------------------

    async def _compute_luck(
        self,
        guild_id: int,
        user_id: int,
        user: dict,
        registry: list[dict],
    ) -> tuple[float, list[str]]:
        """Total luck multiplier + human-readable sources."""
        multiplier = 1.0
        sources: list[str] = []

        if user["equipped_aura_id"]:
            aura = next(
                (i for i in registry if i["item_id"] == user["equipped_aura_id"]),
                None,
            )
            if aura and aura["luck_multiplier"] > 1.0:
                multiplier *= aura["luck_multiplier"]
                bonus = int(round((aura["luck_multiplier"] - 1) * 100))
                sources.append(f"{aura['icon_emoji']} {aura['name']} (+{bonus}%)")

        buffs = await db.rng_get_buffs(guild_id, user_id)
        labels = {
            "luck_goon": "🍀 Luck Goon",
            "goon_charm": "💫 Goon Charm",
            "goon_relic": "🗿 Goon Relic",
        }
        for buff in buffs:
            multiplier *= buff["multiplier"]
            label = labels.get(buff["buff_type"], buff["buff_type"])
            sources.append(f"{label} (x{buff['multiplier']})")

        events = await db.rng_active_events()
        for event in events:
            multiplier *= event["multiplier"]
            sources.append(f"📢 {event['name']} (x{event['multiplier']})")

        return multiplier, sources

    def _roll_tier(self, luck: float) -> str:
        """Weighted tier roll.

        Folk's weight is left unscaled so luck shifts probability mass upward
        (more luck = better chances of leaving Folk) instead of renormalizing
        into a no-op.
        """
        weights = []
        for tier, odds, _ in RNG_TIERS:
            weight = 1.0 / odds
            if tier != TIER_NAMES[0]:
                weight *= luck
            weights.append(weight)
        return random.choices(TIER_NAMES, weights=weights, k=1)[0]

    async def _perform_roll(self, guild_id: int, user_id: int) -> dict:
        """Execute one weighted roll: award item/tokens, update pity and buffs."""
        user = await db.rng_get_user(guild_id, user_id)
        registry = await db.rng_get_registry()
        drop_pool = [i for i in registry if i["base_odds"] is not None and i["item_type"] != "CONSUMABLE"]

        luck, sources = await self._compute_luck(guild_id, user_id, user, registry)
        pity = user["pity_counter"]
        guaranteed = pity >= RNG_PITY_THRESHOLD

        tier: str | None = None
        if guaranteed:
            tier = _tier_above(user["last_drop_tier"])
        if tier is None:
            tier = self._roll_tier(luck)

        pool = [i for i in drop_pool if i["rarity_tier"] == tier]
        if not pool:
            # No items in that tier (shouldn't happen — every tier has items).
            tier = TIER_NAMES[0]
            pool = [i for i in drop_pool if i["rarity_tier"] == tier]
        item = random.choice(pool)

        inventory = await db.rng_get_inventory(guild_id, user_id)
        owned = next((x for x in inventory if x["item_id"] == item["item_id"]), None)
        is_new = owned is None

        extra_tokens = 0
        if is_new:
            await db.rng_add_item(guild_id, user_id, item["item_id"], 1)
        else:
            extra_tokens = item["sell_value"]
            await db.rng_add_tokens(guild_id, user_id, extra_tokens)

        tokens_earned = random.randint(RNG_TOKENS_MIN, RNG_TOKENS_MAX)
        await db.rng_add_tokens(guild_id, user_id, tokens_earned)

        # Pity accounting.
        new_pity = pity
        if guaranteed:
            new_pity = 0
        elif tier in (TIER_NAMES[0], TIER_NAMES[1]):
            new_pity = pity + 1
        else:
            # Natural Samaritano+ drop resets pity unless W Goon protects it.
            has_w_goon = any(x["name"] == "W Goon" and x["quantity"] > 0 for x in inventory)
            if not has_w_goon:
                new_pity = 0

        total_rolls = user["total_rolls"] + 1
        await db.rng_update_user(
            guild_id,
            user_id,
            total_rolls=total_rolls,
            pity_counter=new_pity,
            last_drop_tier=tier,
            last_roll_at=now_iso(),
        )
        await db.rng_tick_roll_buffs(guild_id, user_id)

        return {
            "item": item,
            "tier": tier,
            "is_new": is_new,
            "tokens_earned": tokens_earned,
            "extra_tokens": extra_tokens,
            "pity": new_pity,
            "luck": luck,
            "sources": sources,
            "guaranteed": guaranteed,
            "total_rolls": total_rolls,
        }

    async def _handle_rare_drop(self, guild: discord.Guild, user_id: int, result: dict) -> None:
        """Delegate Goon Master+ drops to the roles/announcements cog."""
        if result["item"]["rarity_tier"] in RNG_ROLE_TIERS:
            roles_cog = self.bot.get_cog("Roles")
            if roles_cog is not None:
                try:
                    await roles_cog.on_rare_drop(guild, user_id, result["item"])
                except Exception:
                    logger.exception("Rare drop handler failed")

    # ------------------------------------------------------------------
    # Auto-roll
    # ------------------------------------------------------------------

    async def start_auto_roll(
        self,
        guild: discord.Guild,
        user: discord.User,
        channel: discord.TextChannel,
    ) -> tuple[bool, str]:
        """Start a timed auto-roll session. Returns (ok, message)."""
        key = (guild.id, user.id)
        if key in self._auto:
            return False, "Ya tienes un auto-roll activo. Detenlo desde /inventory."

        ends_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=RNG_AUTO_DURATION)
        task = self.bot.create_background_task(
            self._auto_loop(guild.id, user.id, channel.id, ends_at)
        )
        self._auto[key] = task
        minutes = int(RNG_AUTO_DURATION / 60)
        return True, f"🔁 Auto-roll activado durante **{minutes} min** (cada {RNG_AUTO_COOLDOWN}s). Solo se publican los desbloqueos nuevos."

    async def stop_auto(self, guild_id: int, user_id: int) -> bool:
        """Cancel an active auto-roll session. Returns True if one was running."""
        task = self._auto.get((guild_id, user_id))
        if task is None:
            return False
        task.cancel()
        return True

    def is_auto_active(self, guild_id: int, user_id: int) -> bool:
        return (guild_id, user_id) in self._auto

    async def _auto_loop(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int,
        ends_at: datetime.datetime,
    ) -> None:
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        member = guild.get_member(user_id) if guild else None

        stats = {"rolls": 0, "unlocks": 0, "tokens": 0, "best": None}
        completed = False

        try:
            while datetime.datetime.utcnow() < ends_at:
                result = await self._perform_roll(guild_id, user_id)
                stats["rolls"] += 1
                stats["tokens"] += result["tokens_earned"] + result["extra_tokens"]
                if result["is_new"]:
                    stats["unlocks"] += 1
                    if stats["best"] is None or tier_index(result["tier"]) > tier_index(stats["best"]):
                        stats["best"] = result["tier"]
                    if member is not None and channel is not None:
                        try:
                            await channel.send(embed=_roll_embed(member, result))
                        except discord.HTTPException:
                            pass
                    if guild is not None:
                        await self._handle_rare_drop(guild, user_id, result)
                await asyncio.sleep(RNG_AUTO_COOLDOWN)
            completed = True
        except asyncio.CancelledError:
            # /roll stop or shutdown — post a summary of what happened.
            raise
        except Exception:
            logger.exception("Auto-roll loop crashed for %s/%s", guild_id, user_id)
        finally:
            self._auto.pop((guild_id, user_id), None)
            if member is not None and channel is not None:
                try:
                    await channel.send(embed=_auto_summary_embed(member, stats, completed))
                except discord.HTTPException:
                    pass

    # ------------------------------------------------------------------
    # Commands: /roll
    # ------------------------------------------------------------------

    @app_commands.command(name="roll", description="Tira el gacha GoonBot (15s de enfriamiento)")
    async def roll(self, interaction: discord.Interaction) -> None:
        """Manual roll. Blocked while an auto-roll session is active."""
        if interaction.guild_id is None or interaction.guild is None:
            await interaction.response.send_message("❌ Solo funciona dentro de un servidor.", ephemeral=True)
            return
        if self.is_auto_active(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "⏳ Estás en auto-roll. Detenlo desde `/inventory` para tirar manualmente.",
                ephemeral=True,
            )
            return

        user = await db.rng_get_user(interaction.guild_id, interaction.user.id)
        remaining = 0.0
        if user["last_roll_at"]:
            last = datetime.datetime.fromisoformat(user["last_roll_at"])
            remaining = max(0.0, RNG_MANUAL_COOLDOWN - (datetime.datetime.utcnow() - last).total_seconds())
        if remaining > 0:
            await interaction.response.send_message(
                f"⏳ Espera **{remaining:.0f}s** para volver a tirar.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        result = await self._perform_roll(interaction.guild_id, interaction.user.id)
        await interaction.followup.send(embed=_roll_embed(interaction.user, result))
        await self._handle_rare_drop(interaction.guild, interaction.user.id, result)

    # ------------------------------------------------------------------
    # Commands: /balance
    # ------------------------------------------------------------------

    @app_commands.command(name="tokens", description="Tu saldo de GoonBot Tokens, pity y suerte")
    async def tokens(self, interaction: discord.Interaction) -> None:
        """Personal token balance, pity progress, equipped aura and buffs."""
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ Solo funciona dentro de un servidor.", ephemeral=True)
            return

        user = await db.rng_get_user(interaction.guild_id, interaction.user.id)
        registry = await db.rng_get_registry()
        luck, sources = await self._compute_luck(interaction.guild_id, interaction.user.id, user, registry)

        embed = discord.Embed(
            title=f"💰 Balance de {interaction.user.display_name}",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Tokens",
            value=f"{GOONBOT_TOKEN_EMOJI} **{user['currency_balance']}**",
            inline=True,
        )
        embed.add_field(name="🎲 Rolls totales", value=str(user["total_rolls"]), inline=True)
        embed.add_field(
            name="Pity",
            value=f"`{_luck_bar(user['pity_counter'])}` {user['pity_counter']}/{RNG_PITY_THRESHOLD}",
            inline=False,
        )

        aura = None
        if user["equipped_aura_id"]:
            aura = next((i for i in registry if i["item_id"] == user["equipped_aura_id"]), None)
        embed.add_field(
            name="Equipado",
            value=f"{aura['icon_emoji']} {aura['name']} ({aura['rarity_tier']})" if aura else "*(nada)*",
            inline=True,
        )
        embed.add_field(
            name="Suerte actual",
            value=f"x{luck:.2f}" + (f"\n{', '.join(sources[:5])}" if sources else ""),
            inline=False,
        )
        embed.add_field(
            name="Último drop",
            value=user["last_drop_tier"] or "*(nunca)*",
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # Commands: /shop
    # ------------------------------------------------------------------

    async def _shop_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        items = await db.rng_get_shop_items()
        return [
            app_commands.Choice(
                name=f"{i['icon_emoji']} {i['name']} — {i['shop_price']} tokens",
                value=str(i["item_id"]),
            )
            for i in items
            if current.lower() in i["name"].lower()
        ][:25]

    @shop_group.command(name="list", description="Ver la tienda")
    async def shop_list(self, interaction: discord.Interaction) -> None:
        """Muestra la tienda con los precios en GoonBot Tokens."""
        items = await db.rng_get_shop_items()
        embed = discord.Embed(
            title=f"🛒 Tienda GoonBot — {GOONBOT_TOKEN_EMOJI}",
            description="Compra con `/shop buy <objeto>`",
            color=discord.Color.gold(),
        )
        for item in items:
            embed.add_field(
                name=f"{item['icon_emoji']} {item['name']} — {item['shop_price']} tokens",
                value=item["description"],
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @shop_group.command(name="buy", description="Compra un objeto con GoonBot Tokens")
    @app_commands.autocomplete(item=_shop_autocomplete)
    @app_commands.describe(item="Objeto de la tienda")
    async def shop_buy(self, interaction: discord.Interaction, item: str) -> None:
        """Compra un objeto: descuenta tokens y lo mete en el inventario."""
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ Solo funciona dentro de un servidor.", ephemeral=True)
            return

        try:
            item_id = int(item)
        except ValueError:
            await interaction.response.send_message("❌ Objeto inválido.", ephemeral=True)
            return

        registry = await db.rng_get_registry()
        shop_item = next((i for i in registry if i["item_id"] == item_id and i["shop_price"] is not None), None)
        if shop_item is None:
            await interaction.response.send_message("❌ Ese objeto no está en la tienda.", ephemeral=True)
            return

        ok = await db.rng_spend_tokens(interaction.guild_id, interaction.user.id, shop_item["shop_price"])
        if not ok:
            await interaction.response.send_message(
                f"❌ No te alcanzan los tokens: necesitas **{shop_item['shop_price']}** {GOONBOT_TOKEN_EMOJI}.",
                ephemeral=True,
            )
            return

        await db.rng_add_item(interaction.guild_id, interaction.user.id, shop_item["item_id"], 1)
        await interaction.response.send_message(
            f"✅ Compraste **{shop_item['icon_emoji']} {shop_item['name']}** por {shop_item['shop_price']} {GOONBOT_TOKEN_EMOJI}."
            " Está en tu inventario (`/inventory`).",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # Commands: /rng event (admin)
    # ------------------------------------------------------------------

    @event_group.command(name="start", description="Inicia un evento global de suerte")
    @app_commands.describe(
        name="Nombre del evento",
        multiplier="Multiplicador de suerte (ej. 2.0 = doble)",
        hours="Duración en horas",
    )
    async def event_start(
        self,
        interaction: discord.Interaction,
        name: str,
        multiplier: float,
        hours: float,
    ) -> None:
        """Crea un evento global que multiplica la suerte de todos."""
        if multiplier < 1.0 or hours <= 0:
            await interaction.response.send_message("❌ Multiplicador ≥ 1 y horas > 0.", ephemeral=True)
            return
        ends_at = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
        await db.rng_start_event(name, multiplier, ends_at.isoformat())
        await interaction.response.send_message(
            f"📢 Evento **{name}** activado: suerte x{multiplier} durante {hours}h.",
            ephemeral=True,
        )

    @event_group.command(name="stop", description="Detiene un evento global")
    @app_commands.describe(event_id="ID del evento (usa /rng event list)")
    async def event_stop(self, interaction: discord.Interaction, event_id: int) -> None:
        await db.rng_stop_event(event_id)
        await interaction.response.send_message(f"🛑 Evento #{event_id} detenido.", ephemeral=True)

    @event_group.command(name="list", description="Lista los eventos activos")
    async def event_list(self, interaction: discord.Interaction) -> None:
        events = await db.rng_active_events()
        if not events:
            await interaction.response.send_message("📭 No hay eventos activos.", ephemeral=True)
            return
        lines = [
            f"`#{e['event_id']}` **{e['name']}** — x{e['multiplier']} hasta {e['ends_at'][:16].replace('T', ' ')}"
            for e in events
        ]
        await interaction.response.send_message("📢 **Eventos activos:**\n" + "\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Rng(bot))
