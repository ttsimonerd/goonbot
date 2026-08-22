"""Interactive /gacha menus — daily, missions, collection, craft, leaderboard.

Every menu edits the same message via buttons (no chat spam): views are
rebuilt from fresh DB state on each interaction, like the inventory UI.
"""

from __future__ import annotations

import datetime
import logging

import discord
from discord import app_commands
from discord.ext import commands

import db
from config import (
    GOONBOT_TOKEN_EMOJI,
    RNG_CRAFT_RECIPES,
    RNG_DAILY_BASE,
    RNG_DAILY_CAP,
    RNG_DAILY_STREAK_BONUS,
    RNG_MISSIONS,
)
from cogs.rng_engine import TIER_NAMES, _luck_bar

logger = logging.getLogger(__name__)

_MISSION_BY_ID = {m["id"]: m for m in RNG_MISSIONS}
_TOP_LABELS = {"tokens": "💰 Tokens", "rolls": "🎲 Rolls", "collection": "📚 Colección"}


def _drop_items(registry: list[dict]) -> list[dict]:
    """The rollable items (excludes shop-only consumables)."""
    return [i for i in registry if i["base_odds"] is not None and i["item_type"] != "CONSUMABLE"]


# ---------------------------------------------------------------------------
# Daily reward
# ---------------------------------------------------------------------------

class DailyView(discord.ui.View):
    """Claim button for the daily login reward."""

    def __init__(self, cog: "GachaUI", guild_id: int, user_id: int, claimed_today: bool) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        button = discord.ui.Button(
            label="🎁 Reclamar",
            style=discord.ButtonStyle.success,
            disabled=claimed_today,
        )
        button.callback = self._on_claim
        self.add_item(button)

    async def _on_claim(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No es tu recompensa.", ephemeral=True)
            return
        today = datetime.date.today().isoformat()
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        result = await db.rng_claim_daily(
            self.guild_id,
            self.user_id,
            today,
            yesterday,
            RNG_DAILY_BASE,
            RNG_DAILY_STREAK_BONUS,
            RNG_DAILY_CAP,
        )
        state = await db.rng_get_daily(self.guild_id, self.user_id)
        embed = self.cog._daily_embed(interaction.user, state, claimed_today=True)
        view = DailyView(self.cog, self.guild_id, self.user_id, claimed_today=True)
        await interaction.response.edit_message(embed=embed, view=view)
        if result["claimed"]:
            await interaction.followup.send(
                f"🎁 ¡+{result['reward']} {GOONBOT_TOKEN_EMOJI}! Racha: **{result['streak']} días**. "
                f"Saldo: {result['balance']} {GOONBOT_TOKEN_EMOJI}.",
                ephemeral=True,
            )


# ---------------------------------------------------------------------------
# Daily missions
# ---------------------------------------------------------------------------

class MissionsView(discord.ui.View):
    """One claim button per completed mission."""

    def __init__(self, cog: "GachaUI", guild_id: int, user_id: int, missions: list[dict]) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        for mission in missions:
            if mission["claimed"] or mission["progress"] < mission["target"]:
                continue
            button = discord.ui.Button(
                label=f"Reclamar {mission['reward']} tok",
                custom_id=f"gacha_mission_{mission['id']}",
                style=discord.ButtonStyle.success,
            )
            button.callback = self._make_claim(mission["id"])
            self.add_item(button)

    def _make_claim(self, mission_id: str):
        async def cb(interaction: discord.Interaction, mid: str = mission_id) -> None:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ No son tus misiones.", ephemeral=True)
                return
            mission = _MISSION_BY_ID[mid]
            today = datetime.date.today().isoformat()
            reward = await db.rng_claim_mission(
                self.guild_id,
                self.user_id,
                today,
                mid,
                mission["target"],
                mission["reward"],
            )
            if reward is None:
                await interaction.response.send_message("❌ Aún no está completa.", ephemeral=True)
                return
            await self.cog._render_missions(interaction, self.guild_id, self.user_id)
            await interaction.followup.send(
                f"✅ Misión completada: **+{reward} {GOONBOT_TOKEN_EMOJI}**",
                ephemeral=True,
            )
        return cb


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

class CollectionView(discord.ui.View):
    """Tier tabs — click a tier to see its items in the same message."""

    def __init__(
        self,
        cog: "GachaUI",
        guild_id: int,
        user_id: int,
        tier: str,
    ) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        for idx, name in enumerate(TIER_NAMES):
            button = discord.ui.Button(
                label=name,
                custom_id=f"gacha_col_{idx}",
                style=discord.ButtonStyle.primary if name == tier else discord.ButtonStyle.secondary,
            )
            button.callback = self._make_tab(name)
            self.add_item(button)

    def _make_tab(self, tier: str):
        async def cb(interaction: discord.Interaction, t: str = tier) -> None:
            await self.cog._render_collection(interaction, self.guild_id, self.user_id, t)
        return cb


# ---------------------------------------------------------------------------
# Crafting
# ---------------------------------------------------------------------------

class ConfirmCraftView(discord.ui.View):
    """Confirm before consuming materials."""

    def __init__(self, cog: "GachaUI", guild_id: int, user_id: int, recipe: dict) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.recipe = recipe

    @discord.ui.button(label="✅ Craftear", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No es tu crafteo.", ephemeral=True)
            return
        materials = [(item["item_id"], qty) for item, qty in self.recipe["materials"]]
        ok, msg = await db.rng_craft(
            self.guild_id,
            self.user_id,
            materials,
            self.recipe["product_item"]["item_id"],
        )
        if not ok:
            await self.cog._render_craft(interaction, self.guild_id, self.user_id)
            await interaction.followup.send("❌ No tienes los materiales necesarios.", ephemeral=True)
            return
        product = self.recipe["product_item"]
        await self.cog._render_craft(interaction, self.guild_id, self.user_id)
        await interaction.followup.send(
            f"⚒️ ¡Crafteaste **{product['icon_emoji']} {product['name']}**!",
            ephemeral=True,
        )

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No es tu crafteo.", ephemeral=True)
            return
        await self.cog._render_craft(interaction, self.guild_id, self.user_id)


class CraftView(discord.ui.View):
    """One button per recipe (disabled when materials are missing)."""

    def __init__(self, cog: "GachaUI", guild_id: int, user_id: int, recipes: list[dict]) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        for idx, recipe in enumerate(recipes):
            button = discord.ui.Button(
                label=f"{recipe['emoji']} {recipe['name']}",
                custom_id=f"gacha_craft_{idx}",
                style=discord.ButtonStyle.success if recipe["can"] else discord.ButtonStyle.secondary,
                disabled=not recipe["can"],
            )
            button.callback = self._make_craft(recipe)
            self.add_item(button)

    def _make_craft(self, recipe: dict):
        async def cb(interaction: discord.Interaction, r: dict = recipe) -> None:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ No es tu crafteo.", ephemeral=True)
                return
            mats = ", ".join(f"{qty}× {item['icon_emoji']} {item['name']}" for item, qty in r["materials"])
            embed = discord.Embed(
                title=f"⚒️ Craftear {r['emoji']} {r['name']}",
                description=(
                    f"Vas a consumir: **{mats}**\\n"
                    f"Recibes: **{r['product_item']['icon_emoji']} {r['product_item']['name']}**"
                ),
                color=discord.Color.gold(),
            )
            await interaction.response.edit_message(embed=embed, view=ConfirmCraftView(self.cog, self.guild_id, self.user_id, r))
        return cb


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

class TopView(discord.ui.View):
    """Category tabs (Tokens / Rolls / Collection)."""

    def __init__(self, cog: "GachaUI", guild_id: int, category: str) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        for cat, label in _TOP_LABELS.items():
            button = discord.ui.Button(
                label=label,
                custom_id=f"gacha_top_{cat}",
                style=discord.ButtonStyle.primary if cat == category else discord.ButtonStyle.secondary,
            )
            button.callback = self._make_tab(cat)
            self.add_item(button)

    def _make_tab(self, category: str):
        async def cb(interaction: discord.Interaction, c: str = category) -> None:
            await self.cog._render_top(interaction, self.guild_id, c)
        return cb


# ---------------------------------------------------------------------------
# Cog + command handlers
# ---------------------------------------------------------------------------

class GachaUI(commands.Cog, name="GachaUI"):
    """Menús interactivos del gacha (recompensa diaria, misiones, colección, crafteo, top)."""

    gacha_group = app_commands.Group(name="gacha", description="Menús del gacha GoonBot")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # -- embeds ------------------------------------------------------------

    def _daily_embed(self, user: discord.User, state: dict, claimed_today: bool) -> discord.Embed:
        streak = state["streak"]
        if claimed_today:
            next_reward = min(RNG_DAILY_CAP, RNG_DAILY_BASE + RNG_DAILY_STREAK_BONUS * streak)
            desc = (
                f"Ya reclamaste hoy. ✅\\n"
                f"Vuelve mañana para mantener la racha de **{streak}** días "
                f"y ganar **{next_reward}** {GOONBOT_TOKEN_EMOJI}."
            )
        else:
            yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
            streak_after = streak + 1 if state["last_claim_date"] == yesterday else 1
            reward = min(RNG_DAILY_CAP, RNG_DAILY_BASE + RNG_DAILY_STREAK_BONUS * (streak_after - 1))
            desc = f"¡Reclama hoy para ganar **{reward}** {GOONBOT_TOKEN_EMOJI}!"
            if streak_after > 1:
                desc += f"\\n🔥 Racha actual: **{streak} días** → subirá a **{streak_after}**."
            else:
                desc += "\\n🔥 Empezarás una nueva racha."
        embed = discord.Embed(
            title=f"🎁 Recompensa diaria de {user.display_name}",
            description=desc,
            color=discord.Color.green(),
        )
        embed.add_field(name="🔥 Racha", value=f"**{streak}** días", inline=True)
        return embed

    def _missions_embed(self, user: discord.User, missions: list[dict]) -> discord.Embed:
        lines = []
        for m in missions:
            done = m["progress"] >= m["target"]
            bar = _luck_bar(min(m["progress"], m["target"]), m["target"])
            if m["claimed"]:
                status = "✅ Reclamado"
            elif done:
                status = "🟢 ¡Reclamar!"
            else:
                status = f"⏳ {m['progress']}/{m['target']}"
            lines.append(f"**{m['name']}** — {bar} {m['progress']}/{m['target']} · {status}")
        embed = discord.Embed(
            title=f"📋 Misiones de hoy — {user.display_name}",
            description="\n".join(lines) or "*(sin misiones)*",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Las misiones cambian cada día a medianoche.")
        return embed

    def _collection_embed(
        self,
        user: discord.User,
        tier: str,
        drop_items: list[dict],
        owned: set[int],
    ) -> discord.Embed:
        total = len(drop_items)
        have = len({i["item_id"] for i in drop_items} & owned)
        pct = int(have / total * 100) if total else 0
        embed = discord.Embed(
            title=f"📚 Colección de {user.display_name}",
            description=f"**{have}/{total}** objetos ({pct}%)",
            color=discord.Color.blurple(),
        )
        tier_items = [i for i in drop_items if i["rarity_tier"] == tier]
        lines = [
            f"{i['icon_emoji']} **{i['name']}** ✅" if i["item_id"] in owned else "❓ ???"
            for i in tier_items
        ]
        embed.add_field(name=tier, value="\n".join(lines) or "*(nada en este tier)*", inline=False)
        embed.set_footer(text="Pulsa un tier para ver sus objetos.")
        return embed

    def _craft_embed(self, user: discord.User, recipes: list[dict]) -> discord.Embed:
        lines = []
        for r in recipes:
            mats = ", ".join(f"{qty}× {item['icon_emoji']} {item['name']}" for item, qty in r["materials"])
            lines.append(f"{r['emoji']} **{r['name']}** ← {mats}")
        embed = discord.Embed(
            title=f"⚒️ Crafteo — {user.display_name}",
            description="\n".join(lines) or "*(no hay recetas)*",
            color=discord.Color.gold(),
        )
        embed.set_footer(text="Pulsa una receta para craftearla (los botones grises = faltan materiales).")
        return embed

    def _top_embed(self, guild: discord.Guild, category: str, rows: list[dict], total_items: int) -> discord.Embed:
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(rows, 1):
            member = guild.get_member(row["user_id"])
            label = member.display_name if member else f"<@{row['user_id']}>"
            if category == "tokens":
                value = f"{row['value']} {GOONBOT_TOKEN_EMOJI}"
            elif category == "rolls":
                value = f"{row['value']} rolls"
            else:
                value = f"{int(row['value'] / total_items * 100)}% ({row['value']}/{total_items})"
            prefix = medals[i - 1] if i <= 3 else f"`{i}`"
            lines.append(f"{prefix} **{label}** — {value}")
        embed = discord.Embed(
            title=f"🏆 Top {_TOP_LABELS[category]}",
            description="\n".join(lines) or "*(sin datos todavía)*",
            color=discord.Color.gold(),
        )
        return embed

    # -- renders -----------------------------------------------------------

    async def _render_missions(self, interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
        engine = self.bot.get_cog("Rng")
        assigned = engine._assigned_missions(guild_id, user_id) if engine else []
        today = datetime.date.today().isoformat()
        stored = {r["mission_id"]: r for r in await db.rng_get_missions(guild_id, user_id, today)}
        missions = []
        for mid in assigned:
            definition = _MISSION_BY_ID.get(mid)
            if definition is None:
                continue
            row = stored.get(mid, {"progress": 0, "claimed": False})
            missions.append({**definition, "progress": row["progress"], "claimed": row["claimed"]})
        embed = self._missions_embed(interaction.user, missions)
        view = MissionsView(self, guild_id, user_id, missions)
        if interaction.response.is_done() or interaction.type == discord.InteractionType.component:
            # Button clicks edit the message they live on — never a new one.
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _render_collection(self, interaction: discord.Interaction, guild_id: int, user_id: int, tier: str) -> None:
        registry = await db.rng_get_registry()
        drop_items = _drop_items(registry)
        owned = await db.rng_owned_item_ids(guild_id, user_id)
        embed = self._collection_embed(interaction.user, tier, drop_items, owned)
        view = CollectionView(self, guild_id, user_id, tier)
        if interaction.response.is_done() or interaction.type == discord.InteractionType.component:
            # Button clicks edit the message they live on — never a new one.
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _render_craft(self, interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
        registry = await db.rng_get_registry()
        by_name = {i["name"]: i for i in registry}
        owned = {x["item_id"]: x["quantity"] for x in await db.rng_get_inventory(guild_id, user_id)}
        recipes = []
        for recipe in RNG_CRAFT_RECIPES:
            materials = []
            can = True
            for name, qty in recipe["materials"]:
                item = by_name.get(name)
                if item is None:
                    can = False
                    continue
                materials.append((item, qty))
                if owned.get(item["item_id"], 0) < qty:
                    can = False
            product_item = by_name.get(recipe["product"])
            if product_item is None:
                can = False
            recipes.append({**recipe, "materials": materials, "product_item": product_item, "can": can})
        embed = self._craft_embed(interaction.user, recipes)
        view = CraftView(self, guild_id, user_id, recipes)
        if interaction.response.is_done() or interaction.type == discord.InteractionType.component:
            # Button clicks edit the message they live on — never a new one.
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _render_top(self, interaction: discord.Interaction, guild_id: int, category: str) -> None:
        guild = interaction.guild
        total_items = len(_drop_items(await db.rng_get_registry()))
        rows = await db.rng_leaderboard(guild_id, category)
        embed = self._top_embed(guild, category, rows, total_items)
        view = TopView(self, guild_id, category)
        if interaction.response.is_done() or interaction.type == discord.InteractionType.component:
            # Button clicks edit the message they live on — never a new one.
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    # -- commands ----------------------------------------------------------

    @gacha_group.command(name="daily", description="Reclama tu recompensa diaria del gacha")
    async def gacha_daily(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ Solo funciona dentro de un servidor.", ephemeral=True)
            return
        today = datetime.date.today().isoformat()
        state = await db.rng_get_daily(interaction.guild_id, interaction.user.id)
        claimed_today = state["last_claim_date"] == today
        embed = self._daily_embed(interaction.user, state, claimed_today)
        view = DailyView(self, interaction.guild_id, interaction.user.id, claimed_today)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @gacha_group.command(name="missions", description="Tus misiones diarias del gacha")
    async def gacha_missions(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ Solo funciona dentro de un servidor.", ephemeral=True)
            return
        await self._render_missions(interaction, interaction.guild_id, interaction.user.id)

    @gacha_group.command(name="collection", description="Tu colección de objetos del gacha")
    async def gacha_collection(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ Solo funciona dentro de un servidor.", ephemeral=True)
            return
        await self._render_collection(interaction, interaction.guild_id, interaction.user.id, TIER_NAMES[0])

    @gacha_group.command(name="craft", description="Craftea objetos con tus materiales")
    async def gacha_craft(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ Solo funciona dentro de un servidor.", ephemeral=True)
            return
        await self._render_craft(interaction, interaction.guild_id, interaction.user.id)

    @gacha_group.command(name="top", description="Top del servidor (tokens, rolls, colección)")
    async def gacha_top(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ Solo funciona dentro de un servidor.", ephemeral=True)
            return
        await self._render_top(interaction, interaction.guild_id, "tokens")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GachaUI(bot))
