"""Interactive inventory UI — ephemeral /inventory view.

A filter Select (by item type) plus an item Select, with action buttons that
change depending on the selected item's category:
  - Equippable: Equip / Unequip
  - Consumable: Use (Luck Goon, Auto-Goon, Goon Charm, Pity Boost, Re-Goon)
  - Anything not equipped: Sell for tokens
  - A Stop button appears while the user's auto-roll is running.
"""

from __future__ import annotations

import datetime
import logging

import discord
from discord import app_commands
from discord.ext import commands

import db
from config import GOONBOT_TOKEN_EMOJI, RNG_PITY_THRESHOLD, RNG_ROLE_TIERS

logger = logging.getLogger(__name__)

_CATEGORY_EMOJIS = {
    "ALL": "📦",
    "EQUIPPABLE": "🔮",
    "CONSUMABLE": "🧪",
    "MATERIAL": "🧱",
    "RELIC": "⚱️",
}

_CATEGORY_LABELS = {
    "ALL": "Todo",
    "EQUIPPABLE": "Equipables",
    "CONSUMABLE": "Consumibles",
    "MATERIAL": "Materiales",
    "RELIC": "Reliquias",
}


class InventoryView(discord.ui.View):
    """Rebuilt from scratch on every interaction (state lives in the DB)."""

    def __init__(
        self,
        cog: "Inventory",
        guild_id: int,
        user_id: int,
        inventory: list[dict],
        category: str,
        item_id: int | None,
    ) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.category = category
        self.item_id = item_id
        self.message: discord.Message | None = None

        # --- Category filter ---
        category_select = discord.ui.Select(
            placeholder="Filtrar por tipo",
            options=[
                discord.SelectOption(
                    label=_CATEGORY_LABELS[key],
                    value=key,
                    emoji=_CATEGORY_EMOJIS[key],
                    default=category == key,
                )
                for key in ("ALL", "EQUIPPABLE", "CONSUMABLE", "MATERIAL", "RELIC")
            ],
        )
        category_select.callback = self._on_category
        self.add_item(category_select)

        # --- Item picker within the filtered category ---
        filtered = [
            x for x in inventory if category == "ALL" or x["item_type"] == category
        ]
        if filtered:
            options = []
            for x in filtered[:25]:
                label = f"{x['icon_emoji']} {x['name']} (x{x['quantity']})"
                if x["is_equipped"]:
                    label += " ✅"
                options.append(
                    discord.SelectOption(
                        label=label[:100],
                        value=str(x["item_id"]),
                        default=item_id == x["item_id"],
                    )
                )
            item_select = discord.ui.Select(placeholder="Elegir objeto", options=options)
            item_select.callback = self._on_item
            self.add_item(item_select)

        # --- Action buttons for the selected item ---
        selected = next((x for x in filtered if x["item_id"] == item_id), None)
        if selected is not None:
            if selected["item_type"] == "EQUIPPABLE":
                if selected["is_equipped"]:
                    self._add_button("Unequip", "Unequip", discord.ButtonStyle.secondary, self._on_unequip)
                else:
                    self._add_button("Equip", "Equip", discord.ButtonStyle.primary, self._on_equip)
            if selected["item_type"] == "CONSUMABLE" and selected["quantity"] > 0:
                self._add_button("Use", "Use", discord.ButtonStyle.success, self._on_use)
            if not selected["is_equipped"]:
                self._add_button("Sell", "Sell", discord.ButtonStyle.danger, self._on_sell)

        # --- Stop auto-roll while one is running ---
        engine = self.cog.bot.get_cog("Rng")
        if engine is not None and engine.is_auto_active(guild_id, user_id):
            self._add_button("Stop Auto", "stop_auto", discord.ButtonStyle.danger, self._on_stop_auto)

    def _add_button(
        self,
        label: str,
        custom_id: str,
        style: discord.ButtonStyle,
        callback,
    ) -> None:
        button = discord.ui.Button(label=label, custom_id=f"rng_{custom_id}", style=style)
        button.callback = callback
        self.add_item(button)

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    async def _refresh(self, interaction: discord.Interaction, category: str, item_id: int | None) -> None:
        await self.cog._render(interaction, self.guild_id, self.user_id, category, item_id)

    async def _on_category(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No es tu inventario.", ephemeral=True)
            return
        await self._refresh(interaction, interaction.data["values"][0], None)

    async def _on_item(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No es tu inventario.", ephemeral=True)
            return
        await self._refresh(interaction, self.category, int(interaction.data["values"][0]))

    async def _on_equip(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id or self.item_id is None:
            return
        await db.rng_set_equipped(self.guild_id, self.user_id, self.item_id)
        await self._refresh_after(interaction, "✅ Aura equipada.")

    async def _on_unequip(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            return
        await db.rng_set_equipped(self.guild_id, self.user_id, None)
        await self._refresh_after(interaction, "✅ Aura desequipada.")

    async def _on_sell(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id or self.item_id is None:
            return
        inventory = await db.rng_get_inventory(self.guild_id, self.user_id)
        item = next((x for x in inventory if x["item_id"] == self.item_id), None)
        if item is None:
            await interaction.response.send_message("❌ Ya no tienes ese objeto.", ephemeral=True)
            return
        if item["is_equipped"]:
            await interaction.response.send_message("❌ No puedes vender el aura equipada.", ephemeral=True)
            return

        ok = await db.rng_remove_item(self.guild_id, self.user_id, self.item_id, 1)
        if not ok:
            await interaction.response.send_message("❌ No tienes suficiente cantidad.", ephemeral=True)
            return
        await db.rng_add_tokens(self.guild_id, self.user_id, item["sell_value"])

        if item["rarity_tier"] in RNG_ROLE_TIERS:
            roles_cog = self.cog.bot.get_cog("Roles")
            if roles_cog is not None:
                try:
                    await roles_cog.on_sold(interaction.guild, self.user_id, item)
                except Exception:
                    logger.exception("Role removal on sell failed")

        await self._refresh_after(
            interaction,
            f"💸 Vendiste **{item['icon_emoji']} {item['name']}** por {item['sell_value']} {GOONBOT_TOKEN_EMOJI}.",
        )

    async def _on_use(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id or self.item_id is None:
            return
        inventory = await db.rng_get_inventory(self.guild_id, self.user_id)
        item = next((x for x in inventory if x["item_id"] == self.item_id), None)
        if item is None or item["quantity"] < 1:
            await interaction.response.send_message("❌ Ya no te queda ninguno.", ephemeral=True)
            return

        guild = interaction.guild
        message, consumed, result_embed = await self.cog._apply_consumable(
            interaction, guild, self.user_id, self.item_id, item
        )

        if consumed:
            await db.rng_remove_item(self.guild_id, self.user_id, self.item_id, 1)
        await self._refresh_after(interaction, message)
        if result_embed is not None:
            try:
                await interaction.followup.send(
                    "🎲 **Re-Goon**: roll gratis del día.",
                    embed=result_embed,
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass

    async def _on_stop_auto(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            return
        engine = self.cog.bot.get_cog("Rng")
        stopped = False
        if engine is not None:
            stopped = await engine.stop_auto(self.guild_id, self.user_id)
        msg = "🛑 Auto-roll detenido." if stopped else "⚠️ No había auto-roll activo."
        await self._refresh_after(interaction, msg)

    async def _refresh_after(self, interaction: discord.Interaction, message: str) -> None:
        """Rebuild the view with a confirmation message on top."""
        await self.cog._render(interaction, self.guild_id, self.user_id, self.category, self.item_id)
        try:
            await interaction.followup.send(message, ephemeral=True)
        except discord.HTTPException:
            pass


class Inventory(commands.Cog, name="Inventory"):
    """Inventario interactivo del gacha RNG."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    async def _render(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        user_id: int,
        category: str,
        item_id: int | None,
    ) -> None:
        inventory = await db.rng_get_inventory(guild_id, user_id)
        user = await db.rng_get_user(guild_id, user_id)
        embed = self._build_embed(interaction.user, user, inventory, category, item_id)
        view = InventoryView(self, guild_id, user_id, inventory, category, item_id)

        if interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = interaction.message

    def _build_embed(
        self,
        user: discord.User,
        user_row: dict,
        inventory: list[dict],
        category: str,
        item_id: int | None,
    ) -> discord.Embed:
        counts = {t: 0 for t in ("EQUIPPABLE", "CONSUMABLE", "MATERIAL", "RELIC")}
        for x in inventory:
            counts[x["item_type"]] += 1

        embed = discord.Embed(
            title=f"🎒 Inventario de {user.display_name}",
            description=(
                f"{GOONBOT_TOKEN_EMOJI} **{user_row['currency_balance']}** tokens · "
                f"Pity `{user_row['pity_counter']}/{RNG_PITY_THRESHOLD}`\n"
                f"🔮 {counts['EQUIPPABLE']} · 🧪 {counts['CONSUMABLE']} · "
                f"🧱 {counts['MATERIAL']} · ⚱️ {counts['RELIC']}"
            ),
            color=discord.Color.blurple(),
        )

        filtered = [x for x in inventory if category == "ALL" or x["item_type"] == category]
        if filtered:
            lines = []
            for x in filtered[:20]:
                equipped = " ✅" if x["is_equipped"] else ""
                lines.append(
                    f"`{x['icon_emoji']}` **{x['name']}** x{x['quantity']} — {x['rarity_tier']}{equipped}"
                )
            if len(filtered) > 20:
                lines.append(f"*…y {len(filtered) - 20} más.*")
            embed.add_field(
                name=f"{_CATEGORY_EMOJIS[category]} {_CATEGORY_LABELS[category]}",
                value="\n".join(lines),
                inline=False,
            )
        else:
            embed.add_field(
                name=f"{_CATEGORY_EMOJIS[category]} {_CATEGORY_LABELS[category]}",
                value="*(nada por aquí)*",
                inline=False,
            )

        selected = next((x for x in filtered if x["item_id"] == item_id), None)
        if selected is not None:
            embed.add_field(
                name="🔍 Seleccionado",
                value=(
                    f"{selected['icon_emoji']} **{selected['name']}**\n"
                    f"{selected['description']}\n"
                    f"Valor de venta: {selected['sell_value']} {GOONBOT_TOKEN_EMOJI}"
                ),
                inline=False,
            )
        else:
            embed.set_footer(text="Elige un objeto para ver sus acciones.")

        return embed

    # ------------------------------------------------------------------
    # Consumable effects
    # ------------------------------------------------------------------

    async def _apply_consumable(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild | None,
        user_id: int,
        item_id: int,
        item: dict,
    ) -> tuple[str, bool, discord.Embed | None]:
        """Apply a consumable's effect.

        Returns (message, should_consume, optional_result_embed). The embed is
        returned instead of sent so the caller can respond to the interaction
        first (component interactions must be responded to before followups).
        """
        if guild is None or guild.id is None:
            return "❌ Solo funciona en servidores.", False, None

        name = item["name"]
        now = datetime.datetime.utcnow()

        if name == "Luck Goon":
            expires = (now + datetime.timedelta(minutes=10)).isoformat()
            await db.rng_add_buff(guild.id, user_id, "luck_goon", 1.5, expires_at=expires)
            return "🍀 **Luck Goon** activado: +50% suerte durante 10 min.", True, None

        if name == "Auto-Goon":
            engine = self.bot.get_cog("Rng")
            if engine is None:
                return "❌ Motor RNG no disponible.", False, None
            ok, msg = await engine.start_auto_roll(guild, interaction.user, interaction.channel)
            return msg, ok, None

        if name == "Goon Charm":
            await db.rng_add_buff(guild.id, user_id, "goon_charm", 1.25, rolls_left=20)
            return "💫 **Goon Charm** activado: +25% suerte durante 20 rolls.", True, None

        if name == "Pity Boost":
            user = await db.rng_get_user(guild.id, user_id)
            await db.rng_update_user(
                guild.id,
                user_id,
                pity_counter=user["pity_counter"] + 25,
            )
            return "🚀 **Pity Boost** aplicado: +25 puntos de pity.", True, None

        if name == "Re-Goon":
            if not await db.rng_can_use(guild.id, user_id, "re_goon"):
                return "❌ Ya usaste tu **Re-Goon** de hoy. Vuelve mañana.", False, None
            await db.rng_mark_use(guild.id, user_id, "re_goon")
            engine = self.bot.get_cog("Rng")
            if engine is None:
                return "❌ Motor RNG no disponible.", False, None
            result = await engine._perform_roll(guild.id, user_id)
            embed = engine._roll_embed(interaction.user, result)
            return "🎲 Re-Goon usado (roll gratis del día).", True, embed

        return "❌ Ese objeto no se puede usar.", False, None

    # ------------------------------------------------------------------
    # Command: /inventory
    # ------------------------------------------------------------------

    @app_commands.command(name="inventory", description="Abre tu inventario RNG (ephemeral)")
    async def inventory(self, interaction: discord.Interaction) -> None:
        """Inventario efímero con filtros y acciones por objeto."""
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ Solo funciona dentro de un servidor.", ephemeral=True)
            return
        await self._render(interaction, interaction.guild_id, interaction.user.id, "ALL", None)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Inventory(bot))
