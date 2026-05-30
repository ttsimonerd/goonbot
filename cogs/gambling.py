import os
import json
import random
import asyncio
import datetime
import uuid
from collections import Counter
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# ---------------------
# Data file
# ---------------------
DATA_FILE = "gambling_data.json"
SETTINGS_FILE = "settings.json"


# ---------------------
# Helpers
# ---------------------
def load_settings() -> dict:
    defaults = {
        "gambling_channel_id": None,
        "gambling_lockout_hours": 24,
        "gambling_max_warns": 3,
        "gambling_winners_channel_id": None,
    }
    if not os.path.exists(SETTINGS_FILE):
        return defaults
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            for k, v in defaults.items():
                if k not in data:
                    data[k] = v
            return data
        except json.JSONDecodeError:
            return defaults


def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_user_data(data: dict, guild_id: int, user_id: int) -> dict:
    gid = str(guild_id)
    uid = str(user_id)
    if gid not in data:
        data[gid] = {}
    if uid not in data[gid]:
        data[gid][uid] = {
            "warns": 0,
            "locked_until": None,
            "money": 100,
            "daily_claimed": None,
        }
    else:
        user = data[gid][uid]
        if "money" not in user:
            user["money"] = 100
        if "daily_claimed" not in user:
            user["daily_claimed"] = None
    return data[gid][uid]


def get_top_balances(data: dict, guild: discord.Guild, limit: int = 5) -> list[tuple[str, int]]:
    gid = str(guild.id)
    if gid not in data:
        return []
    all_users = []
    for uid, info in data[gid].items():
        if uid.startswith("_"):
            continue
        balance = info.get("money", 100)
        all_users.append((uid, balance))
    all_users.sort(key=lambda x: x[1], reverse=True)
    return all_users[:limit]


def format_money(amount: int) -> str:
    return f"{amount:,} coins"


def get_guild_predictions(data: dict, guild_id: int) -> dict:
    gid = str(guild_id)
    if gid not in data:
        data[gid] = {}
    if "_predictions" not in data[gid]:
        data[gid]["_predictions"] = {}
    return data[gid]["_predictions"]


def build_deck() -> list[str]:
    ranks = ["A"] + [str(n) for n in range(2, 11)] + ["J", "Q", "K"]
    suits = ["♥", "♦", "♣", "♠"]
    return [f"{rank}{suit}" for rank in ranks for suit in suits]


def card_value(card: str) -> int:
    rank = card[:-1]
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)


def best_blackjack_total(cards: list[str]) -> int:
    total = sum(card_value(card) for card in cards)
    aces = sum(1 for card in cards if card[:-1] == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def poker_rank(cards: list[str]) -> tuple[int, list[int]]:
    ranks_order = {str(n): n for n in range(2, 11)}
    ranks_order.update({"J": 11, "Q": 12, "K": 13, "A": 14})
    values = sorted([ranks_order[card[:-1]] for card in cards], reverse=True)
    suits = [card[-1] for card in cards]
    flush = len(set(suits)) == 1
    unique = sorted(set(values))
    straight = len(unique) == 5 and unique[0] - unique[-1] == 4
    if unique == [14, 5, 4, 3, 2]:
        straight = True
        values = [5, 4, 3, 2, 1]
    counts = Counter(values)
    counts_sorted = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    count_values = [cnt for val, cnt in counts_sorted]
    sorted_by_count = [val for val, cnt in counts_sorted]

    if straight and flush:
        rank = 8
    elif count_values == [4, 1]:
        rank = 7
    elif count_values == [3, 2]:
        rank = 6
    elif flush:
        rank = 5
    elif straight:
        rank = 4
    elif count_values == [3, 1, 1]:
        rank = 3
    elif count_values == [2, 2, 1]:
        rank = 2
    elif count_values == [2, 1, 1, 1]:
        rank = 1
    else:
        rank = 0

    return rank, sorted_by_count + values


def hand_rank_name(rank: int) -> str:
    names = [
        "High Card",
        "One Pair",
        "Two Pair",
        "Three of a Kind",
        "Straight",
        "Flush",
        "Full House",
        "Four of a Kind",
        "Straight Flush"
    ]
    return names[rank]


def roulette_color(number: int) -> str:
    if number == 0:
        return "green"
    red_numbers = {
        1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36
    }
    return "red" if number in red_numbers else "black"


def predict_multiplier(days: int) -> float:
    return 1.0 + 0.15 * min(days, 20)


def predict_success_chance(days: int) -> float:
    return max(0.2, 0.85 - 0.03 * min(days, 20))


# ---------------------
# Cog
# ---------------------
class Gambling(commands.Cog, name="Gambling"):
    """Russian Roulette y sistema de warns para el canal de gambling."""

    prediction_group = app_commands.Group(
        name="votebet",
        description="Apuestas personalizadas con resolución automática"
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.loop.create_task(self._daily_winners_loop())
        self.bot.loop.create_task(self._prediction_resolution_loop())

    def _get_gambling_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Get gambling channel from settings (by ID) or auto-detect by name."""
        settings = load_settings()
        ch_id = settings.get("gambling_channel_id")
        if ch_id:
            ch = guild.get_channel(ch_id)
            if ch:
                return ch
        # Fallback: auto-detect by name
        for ch in guild.text_channels:
            if "gambling" in ch.name.lower():
                return ch
        return None

    def _get_gambling_winners_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        settings = load_settings()
        ch_id = settings.get("gambling_winners_channel_id")
        if ch_id:
            ch = guild.get_channel(ch_id)
            if ch:
                return ch
        for ch in guild.text_channels:
            name = ch.name.lower()
            if any(keyword in name for keyword in ("winners", "winner", "ganadores", "ganador")):
                return ch
        return None

    async def _post_daily_winners(self):
        data = load_data()
        for guild in self.bot.guilds:
            channel = self._get_gambling_winners_channel(guild)
            if channel is None:
                continue
            top = get_top_balances(data, guild, limit=5)
            if not top:
                continue
            lines = []
            for idx, (uid, balance) in enumerate(top, start=1):
                member = guild.get_member(int(uid))
                display = member.display_name if member else f"User {uid}"
                lines.append(f"**{idx}.** {display} — `{format_money(balance)}`")
            embed = discord.Embed(
                title="🏆 Ganadores diarios de gambling",
                description="\n".join(lines),
                color=discord.Color.gold(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text="¡Enhorabuena a los ganadores de hoy!")
            try:
                await channel.send(embed=embed)
            except Exception as e:
                print(f"[Gambling] Failed to post daily winners in {guild.name}: {e}")

    async def _resolve_due_predictions(self):
        data = load_data()
        now = datetime.datetime.utcnow()
        for guild in self.bot.guilds:
            predictions = get_guild_predictions(data, guild.id)
            channel = self._get_gambling_channel(guild) or self._get_gambling_winners_channel(guild)
            for pid, pred in list(predictions.items()):
                if pred.get("settled"):
                    continue
                resolve_at = datetime.datetime.fromisoformat(pred["resolve_at"])
                if now >= resolve_at:
                    creator_id = int(pred["creator_id"])
                    amount = pred["amount"]
                    multiplier = pred["multiplier"]
                    poll_channel = guild.get_channel(pred.get("channel_id")) if pred.get("channel_id") else None
                    poll_message = None
                    yes_votes = 0
                    no_votes = 0
                    poll_result = None
                    if poll_channel and pred.get("message_id"):
                        try:
                            poll_message = await poll_channel.fetch_message(pred["message_id"])
                            for reaction in poll_message.reactions:
                                emoji = str(reaction.emoji)
                                if emoji == "✅":
                                    yes_votes = max(0, reaction.count - 1)
                                elif emoji == "❌":
                                    no_votes = max(0, reaction.count - 1)
                            if yes_votes > no_votes:
                                poll_result = True
                            elif no_votes > yes_votes:
                                poll_result = False
                        except Exception:
                            poll_result = None

                    if poll_result is None:
                        success = random.random() < pred["success_chance"]
                        poll_basis = "Resolución aleatoria (sin resultado claro de la votación)."
                    else:
                        success = poll_result
                        poll_basis = f"Resolución basada en la votación: ✅ {yes_votes} vs ❌ {no_votes}."

                    user_data = get_user_data(data, guild.id, creator_id)
                    if success:
                        payout = int(amount * multiplier)
                        user_data["money"] += payout
                        result_text = f"✅ {guild.get_member(creator_id).mention if guild.get_member(creator_id) else f'<@{creator_id}>'} ganó {format_money(payout)} en la predicción."
                    else:
                        payout = 0
                        result_text = f"❌ {guild.get_member(creator_id).mention if guild.get_member(creator_id) else f'<@{creator_id}>'} perdió la predicción y no recuperó su apuesta."
                    pred["settled"] = True
                    pred["result"] = "win" if success else "lose"
                    save_data(data)
                    if channel:
                        embed = discord.Embed(
                            title="📣 Predicción resuelta",
                            description=result_text,
                            color=discord.Color.blurple(),
                            timestamp=now
                        )
                        embed.add_field(name="Predicción", value=pred["description"], inline=False)
                        embed.add_field(name="Votos", value=f"✅ {yes_votes} — ❌ {no_votes}", inline=True)
                        embed.add_field(name="Resultado", value="✅ Ganó" if success else "❌ Perdió", inline=True)
                        embed.add_field(name="Multiplicador", value=f"x{multiplier:.2f}", inline=True)
                        embed.add_field(name="Base", value=poll_basis, inline=False)
                        try:
                            await channel.send(embed=embed)
                        except Exception as e:
                            print(f"[Gambling] Failed to post prediction resolution in {guild.name}: {e}")

    async def _prediction_resolution_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await self._resolve_due_predictions()
            await asyncio.sleep(60)

    async def _daily_winners_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.datetime.utcnow()
            tomorrow = now.date() + datetime.timedelta(days=1)
            next_run = datetime.datetime.combine(tomorrow, datetime.time(0, 0, 0))
            wait_seconds = (next_run - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            await self._post_daily_winners()

    async def _lock_channel(self, guild: discord.Guild, user: discord.Member):
        """Removes the user's permission to send messages in the gambling channel."""
        settings = load_settings()
        max_warns = settings.get("gambling_max_warns", 3)
        ch = self._get_gambling_channel(guild)
        if ch is None:
            return
        await ch.set_permissions(
            user,
            send_messages=False,
            reason=f"Gambling ban: {max_warns} warns reached."
        )

    async def _unlock_channel(self, guild_id: int, user_id: int, lockout_hours: int):
        """Restores the user's permissions after lockout expires."""
        await asyncio.sleep(lockout_hours * 3600)
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        ch = self._get_gambling_channel(guild)
        member = guild.get_member(user_id)
        if ch and member:
            await ch.set_permissions(member, send_messages=None, reason="Gambling ban expired.")
        # Clear warns and lockout in data
        data = load_data()
        user_data = get_user_data(data, guild_id, user_id)
        user_data["warns"] = 0
        user_data["locked_until"] = None
        save_data(data)

    @app_commands.command(name="roulette", description="Apuesta en la ruleta y gana según tu elección.")
    @app_commands.describe(
        bet="Cantidad de monedas a apostar",
        choice="Apuesta a red, black, even, odd o green"
    )
    async def roulette(self, interaction: discord.Interaction, bet: int, choice: str | None = None):
        settings = load_settings()
        LOCKOUT_HOURS = settings.get("gambling_lockout_hours", 24)
        MAX_WARNS = settings.get("gambling_max_warns", 3)

        data = load_data()
        user_data = get_user_data(data, interaction.guild_id, interaction.user.id)

        # Check if locked
        locked_until = user_data.get("locked_until")
        if locked_until:
            unlock_dt = datetime.datetime.fromisoformat(locked_until)
            if datetime.datetime.utcnow() < unlock_dt:
                remaining = unlock_dt - datetime.datetime.utcnow()
                hours, rem = divmod(int(remaining.total_seconds()), 3600)
                minutes = rem // 60
                await interaction.response.send_message(
                    f"🔒 Estás baneado del gambling por **{hours}h {minutes}m** más. Piénsatelo dos veces la próxima vez!",
                    ephemeral=True
                )
                return
            else:
                user_data["warns"] = 0
                user_data["locked_until"] = None

        current_money = user_data.get("money", 100)
        if bet <= 0:
            await interaction.response.send_message(
                "❌ Debes apostar una cantidad positiva.", ephemeral=True
            )
            return
        if bet > current_money:
            await interaction.response.send_message(
                f"❌ No tienes suficientes monedas. Tu saldo es {format_money(current_money)}.",
                ephemeral=True
            )
            return

        valid_choices = {"red", "black", "even", "odd", "green"}
        if choice:
            choice = choice.lower().strip()
            if choice not in valid_choices:
                await interaction.response.send_message(
                    "❌ Opción inválida. Usa red, black, even, odd o green.",
                    ephemeral=True
                )
                return
        else:
            choice = random.choice(["red", "black", "even", "odd"])

        wheel = random.randint(0, 36)
        color = roulette_color(wheel)
        win = False
        payout = 0

        if choice == "green":
            win = (wheel == 0)
            payout = bet * 35
        elif choice in {"red", "black"}:
            win = (color == choice)
            payout = bet * 2
        elif choice == "even":
            win = wheel != 0 and wheel % 2 == 0
            payout = bet * 2
        elif choice == "odd":
            win = wheel % 2 == 1
            payout = bet * 2

        if win:
            user_data["money"] = current_money + payout
            result_title = "🎉 Ganaste la ruleta"
            result_desc = (
                f"{interaction.user.mention} apostó {format_money(bet)} a **{choice}** y la bola cayó en **{wheel} {color}**.\n"
                f"Has ganado {format_money(payout)}. Saldo actual: {format_money(user_data['money'])}."
            )
        else:
            user_data["money"] = max(0, current_money - bet)
            user_data["warns"] += 1
            warns = user_data["warns"]
            result_title = "💀 Perdiste la ruleta"
            result_desc = (
                f"{interaction.user.mention} apostó {format_money(bet)} a **{choice}** y la bola cayó en **{wheel} {color}**.\n"
                f"Has perdido la apuesta. Saldo actual: {format_money(user_data['money'])}."
            )
            if warns >= MAX_WARNS:
                locked_until_dt = datetime.datetime.utcnow() + datetime.timedelta(hours=LOCKOUT_HOURS)
                user_data["locked_until"] = locked_until_dt.isoformat()
                await self._lock_channel(interaction.guild, interaction.user)
                self.bot.loop.create_task(
                    self._unlock_channel(interaction.guild_id, interaction.user.id, LOCKOUT_HOURS)
                )
                result_desc += f"\n🔒 Has alcanzado {warns} warns y estás baneado del gambling por {LOCKOUT_HOURS} horas."

        save_data(data)
        embed = discord.Embed(
            title=result_title,
            description=result_desc,
            color=discord.Color.green() if win else discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="blackjack", description="Juega una partida rápida de Blackjack.")
    @app_commands.describe(bet="Cantidad de monedas a apostar")
    async def blackjack(self, interaction: discord.Interaction, bet: int):
        data = load_data()
        user_data = get_user_data(data, interaction.guild_id, interaction.user.id)
        current_money = user_data.get("money", 100)

        if bet <= 0:
            await interaction.response.send_message("❌ Debes apostar una cantidad positiva.", ephemeral=True)
            return
        if bet > current_money:
            await interaction.response.send_message(
                f"❌ No tienes suficientes monedas. Tu saldo es {format_money(current_money)}.",
                ephemeral=True
            )
            return

        user_data["money"] = current_money - bet
        save_data(data)

        deck = build_deck()
        random.shuffle(deck)
        user_cards = [deck.pop(), deck.pop()]
        dealer_cards = [deck.pop(), deck.pop()]

        class BlackjackView(discord.ui.View):
            def __init__(self, author_id: int):
                super().__init__(timeout=120)
                self.author_id = author_id
                self.user_cards = user_cards
                self.dealer_cards = dealer_cards
                self.deck = deck
                self.finished = False

            def update_embed(self, embed: discord.Embed):
                embed.clear_fields()
                embed.add_field(name="Tus cartas", value=" ".join(self.user_cards), inline=False)
                embed.add_field(name="Cartas del dealer", value=f"{self.dealer_cards[0]} ??", inline=False)
                total = best_blackjack_total(self.user_cards)
                embed.set_footer(text=f"Total: {total}")
                return embed

            async def finish(self, interaction: discord.Interaction, result_title: str, description: str, win: bool):
                for child in self.children:
                    child.disabled = True
                self.stop()
                embed = discord.Embed(title=result_title, description=description, color=discord.Color.green() if win else discord.Color.red())
                embed.add_field(name="Tus cartas", value=" ".join(self.user_cards), inline=False)
                embed.add_field(name="Cartas del dealer", value=" ".join(self.dealer_cards), inline=False)
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
            async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("Este juego no es tuyo.", ephemeral=True)
                    return
                self.user_cards.append(self.deck.pop())
                total = best_blackjack_total(self.user_cards)
                if total > 21:
                    await self.finish(interaction, "💥 Te pasaste", f"Has pedido carta y tu total es {total}. Pierdes.", False)
                    return
                embed = discord.Embed(title="Blackjack", description="Elige si quieres otra carta o plantarte.")
                await interaction.response.edit_message(embed=self.update_embed(embed), view=self)

            @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
            async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("Este juego no es tuyo.", ephemeral=True)
                    return
                dealer_total = best_blackjack_total(self.dealer_cards)
                while dealer_total < 17:
                    self.dealer_cards.append(self.deck.pop())
                    dealer_total = best_blackjack_total(self.dealer_cards)
                user_total = best_blackjack_total(self.user_cards)
                if dealer_total > 21 or user_total > dealer_total:
                    winnings = int(bet * 2)
                    data = load_data()
                    user_data = get_user_data(data, interaction.guild_id, interaction.user.id)
                    user_data["money"] += winnings
                    save_data(data)
                    await self.finish(interaction, "🎉 Blackjack ganado", f"Tu total: {user_total}. Dealer: {dealer_total}. Has ganado {format_money(winnings)}.", True)
                else:
                    await self.finish(interaction, "😢 Blackjack perdido", f"Tu total: {user_total}. Dealer: {dealer_total}. Pierdes.", False)

        view = BlackjackView(interaction.user.id)
        embed = discord.Embed(title="Blackjack", description="Tus cartas iniciales.", color=discord.Color.blurple())
        embed = view.update_embed(embed)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="poker", description="Juega una partida rápida de Poker contra la banca.")
    @app_commands.describe(bet="Cantidad de monedas a apostar")
    async def poker(self, interaction: discord.Interaction, bet: int):
        data = load_data()
        user_data = get_user_data(data, interaction.guild_id, interaction.user.id)
        current_money = user_data.get("money", 100)

        if bet <= 0:
            await interaction.response.send_message("❌ Debes apostar una cantidad positiva.", ephemeral=True)
            return
        if bet > current_money:
            await interaction.response.send_message(
                f"❌ No tienes suficientes monedas. Tu saldo es {format_money(current_money)}.",
                ephemeral=True
            )
            return

        user_data["money"] = current_money - bet
        save_data(data)

        deck = build_deck()
        random.shuffle(deck)
        user_cards = [deck.pop() for _ in range(5)]
        dealer_cards = [deck.pop() for _ in range(5)]
        user_rank, user_tiebreak = poker_rank(user_cards)
        dealer_rank, dealer_tiebreak = poker_rank(dealer_cards)

        result = "Empate"
        win = False
        if user_rank > dealer_rank or (user_rank == dealer_rank and user_tiebreak > dealer_tiebreak):
            result = "Ganaste"
            win = True
        elif user_rank < dealer_rank or (user_rank == dealer_rank and user_tiebreak < dealer_tiebreak):
            result = "Perdiste"
        else:
            result = "Empate"
            user_data["money"] += bet
            save_data(data)

        if win:
            payout = int(bet * 2.5)
            user_data["money"] += payout
            save_data(data)
            result_text = f"Has ganado {format_money(payout)}."
        elif result == "Empate":
            result_text = "Empate, recuperas tu apuesta."
        else:
            result_text = "Has perdido la apuesta."

        embed = discord.Embed(title="Poker rápido", color=discord.Color.purple())
        embed.add_field(name="Tu mano", value=" ".join(user_cards), inline=False)
        embed.add_field(name="Mano de la banca", value=" ".join(dealer_cards), inline=False)
        embed.add_field(name="Resultado", value=f"{result} — {hand_rank_name(user_rank)} vs {hand_rank_name(dealer_rank)}", inline=False)
        embed.add_field(name="Detalle", value=result_text, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="balatro", description="Juego de rondas infinitas: sigue hasta perder o cobra tu premio.")
    @app_commands.describe(bet="Cantidad de monedas para iniciar")
    async def balatro(self, interaction: discord.Interaction, bet: int):
        data = load_data()
        user_data = get_user_data(data, interaction.guild_id, interaction.user.id)
        current_money = user_data.get("money", 100)

        if bet <= 0:
            await interaction.response.send_message("❌ Debes apostar una cantidad positiva.", ephemeral=True)
            return
        if bet > current_money:
            await interaction.response.send_message(
                f"❌ No tienes suficientes monedas. Tu saldo es {format_money(current_money)}.",
                ephemeral=True
            )
            return

        user_data["money"] = current_money - bet
        save_data(data)

        class BalatroView(discord.ui.View):
            def __init__(self, round_number: int = 1, multiplier: float = 1.0):
                super().__init__(timeout=120)
                self.round_number = round_number
                self.multiplier = multiplier
                self.bet = bet
                self.finished = False

            def get_reward(self) -> int:
                return int(self.bet * self.multiplier)

            def update_embed(self) -> discord.Embed:
                embed = discord.Embed(
                    title="Balatro",
                    description="Sigue apostando hasta que pierdas o cobra tu premio.",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Ronda", value=str(self.round_number), inline=True)
                embed.add_field(name="Multiplicador", value=f"x{self.multiplier:.2f}", inline=True)
                embed.add_field(name="Recompensa actual", value=format_money(self.get_reward()), inline=False)
                embed.set_footer(text="Pulsa Continuar para intentar otra ronda o Cobrar para llevarte el premio.")
                return embed

            async def finish(self, interaction: discord.Interaction, success: bool, text: str):
                for child in self.children:
                    child.disabled = True
                self.stop()
                if success:
                    payout = self.get_reward()
                    data = load_data()
                    user_data = get_user_data(data, interaction.guild_id, interaction.user.id)
                    user_data["money"] += payout
                    save_data(data)
                    embed = discord.Embed(title="🏆 Cobrado", description=text, color=discord.Color.green())
                    embed.add_field(name="Ganancia", value=format_money(payout), inline=False)
                else:
                    embed = discord.Embed(title="💥 Has perdido", description=text, color=discord.Color.red())
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary)
            async def continue_round(self, interaction: discord.Interaction, button: discord.ui.Button):
                chance = max(0.1, 0.6 - 0.05 * (self.round_number - 1))
                if random.random() < chance:
                    self.round_number += 1
                    self.multiplier += random.uniform(0.25, 0.45)
                    await interaction.response.edit_message(embed=self.update_embed(), view=self)
                else:
                    await self.finish(interaction, False, f"Has perdido en la ronda {self.round_number}."
                    )

            @discord.ui.button(label="Cobrar", style=discord.ButtonStyle.success)
            async def cash_out(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self.finish(interaction, True, f"Has cobrado después de {self.round_number} rondas.")

        view = BalatroView()
        await interaction.response.send_message(embed=view.update_embed(), view=view)

    @prediction_group.command(name="create", description="Crea una apuesta de votación personalizada.")
    @app_commands.describe(
        days="Días para esperar antes de resolver la apuesta",
        amount="Apuesta inicial",
        prediction_description="Descripción de tu predicción"
    )
    async def create_prediction(self, interaction: discord.Interaction, days: int, amount: int, prediction_description: str):
        if amount <= 0:
            await interaction.response.send_message("❌ La apuesta debe ser positiva.", ephemeral=True)
            return
        if days < 1 or days > 30:
            await interaction.response.send_message("❌ Los días deben estar entre 1 y 30.", ephemeral=True)
            return

        data = load_data()
        user_data = get_user_data(data, interaction.guild_id, interaction.user.id)
        current_money = user_data.get("money", 100)
        if amount > current_money:
            await interaction.response.send_message(
                f"❌ No tienes suficientes monedas. Tu saldo es {format_money(current_money)}.",
                ephemeral=True
            )
            return

        user_data["money"] -= amount
        predictions = get_guild_predictions(data, interaction.guild_id)
        bet_id = str(uuid.uuid4())[:8]
        multiplier = predict_multiplier(days)
        predictions[bet_id] = {
            "creator_id": str(interaction.user.id),
            "description": prediction_description,
            "amount": amount,
            "days": days,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "resolve_at": (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat(),
            "multiplier": multiplier,
            "success_chance": predict_success_chance(days),
            "settled": False,
            "result": None,
            "channel_id": None,
            "message_id": None,
        }
        save_data(data)

        poll_channel = self._get_gambling_channel(interaction.guild) or interaction.channel
        if poll_channel is None:
            await interaction.response.send_message(
                "❌ No hay canal disponible para publicar la votación.", ephemeral=True
            )
            return

        resolve_at = datetime.datetime.utcnow() + datetime.timedelta(days=days)
        poll_embed = discord.Embed(
            title="🗳️ Nueva predicción",
            description=prediction_description,
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        poll_embed.add_field(name="ID", value=bet_id, inline=True)
        poll_embed.add_field(name="Creador", value=interaction.user.mention, inline=True)
        poll_embed.add_field(name="Apuesta", value=format_money(amount), inline=True)
        poll_embed.add_field(name="Días", value=str(days), inline=True)
        poll_embed.add_field(name="Resuelve el", value=f"<t:{int(resolve_at.timestamp())}:F>", inline=False)
        poll_embed.add_field(name="Multiplicador", value=f"x{multiplier:.2f}", inline=True)
        poll_embed.add_field(name="Votos", value="✅ Sí / ❌ No", inline=False)
        poll_embed.set_footer(text="Resuelve automáticamente al finalizar los días.")

        try:
            poll_message = await poll_channel.send(embed=poll_embed)
            await poll_message.add_reaction("✅")
            await poll_message.add_reaction("❌")
        except Exception as e:
            user_data["money"] += amount
            save_data(data)
            await interaction.response.send_message(
                f"❌ No se pudo crear la votación: {e}", ephemeral=True
            )
            return

        predictions[bet_id]["channel_id"] = poll_channel.id
        predictions[bet_id]["message_id"] = poll_message.id
        save_data(data)

        embed = discord.Embed(
            title="📈 Apuesta de predicción creada",
            description=prediction_description,
            color=discord.Color.blue()
        )
        embed.add_field(name="ID", value=bet_id, inline=True)
        embed.add_field(name="Apuesta", value=format_money(amount), inline=True)
        embed.add_field(name="Días", value=str(days), inline=True)
        embed.add_field(name="Multiplicador", value=f"x{multiplier:.2f}", inline=True)
        embed.add_field(name="Probabilidad de éxito", value=f"{predict_success_chance(days) * 100:.0f}%", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @prediction_group.command(name="status", description="Consulta tus apuestas de predicción activas.")
    async def prediction_status(self, interaction: discord.Interaction):
        data = load_data()
        predictions = get_guild_predictions(data, interaction.guild_id)
        lines = []
        for pid, pred in predictions.items():
            if pred.get("creator_id") != str(interaction.user.id) or pred.get("settled"):
                continue
            resolve_at = datetime.datetime.fromisoformat(pred["resolve_at"])
            remaining = resolve_at - datetime.datetime.utcnow()
            hours = max(0, int(remaining.total_seconds() // 3600))
            minutes = max(0, int((remaining.total_seconds() % 3600) // 60))
            lines.append(
                f"**{pid}** — {pred['description']} — {format_money(pred['amount'])} — resuelve en {hours}h {minutes}m"
            )
        if not lines:
            await interaction.response.send_message("No tienes apuestas activas.", ephemeral=True)
            return
        embed = discord.Embed(
            title="📊 Tus apuestas activas",
            description="\n".join(lines),
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gambling_warns", description="Consulta los warns de gambling de un usuario.")
    @app_commands.describe(user="Usuario a consultar")
    async def gambling_warns(self, interaction: discord.Interaction, user: discord.Member = None):
        settings = load_settings()
        MAX_WARNS = settings.get("gambling_max_warns", 3)

        target = user or interaction.user
        data = load_data()
        user_data = get_user_data(data, interaction.guild_id, target.id)
        warns = user_data["warns"]
        locked_until = user_data.get("locked_until")

        embed = discord.Embed(
            title=f"📋 Warns de {target.display_name}",
            color=discord.Color.orange()
        )
        embed.add_field(name="Warns", value=f"{warns}/{MAX_WARNS}", inline=True)
        if locked_until:
            unlock_dt = datetime.datetime.fromisoformat(locked_until)
            if datetime.datetime.utcnow() < unlock_dt:
                embed.add_field(name="Estado", value=f"🔒 Baneado hasta <t:{int(unlock_dt.timestamp())}:R>", inline=True)
            else:
                embed.add_field(name="Estado", value="✅ Libre", inline=True)
        else:
            embed.add_field(name="Estado", value="✅ Libre", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gambling_pardon", description="[ADMIN] Perdona los warns de gambling de un usuario.")
    @app_commands.describe(user="Usuario a perdonar")
    @app_commands.default_permissions(administrator=True)
    async def gambling_pardon(self, interaction: discord.Interaction, user: discord.Member):
        data = load_data()
        user_data = get_user_data(data, interaction.guild_id, user.id)
        user_data["warns"] = 0
        user_data["locked_until"] = None
        save_data(data)

        # Restore channel permissions
        ch = self._get_gambling_channel(interaction.guild)
        if ch:
            await ch.set_permissions(user, send_messages=None, reason="Admin pardon.")

        await interaction.response.send_message(
            f"✅ {user.mention} ha sido perdonado. Sus warns han sido borrados y el canal desbloqueado.",
            ephemeral=True
        )

    @app_commands.command(name="balance", description="Muestra tu saldo de gambling.")
    @app_commands.describe(user="Usuario a consultar")
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        data = load_data()
        user_data = get_user_data(data, interaction.guild_id, target.id)
        await interaction.response.send_message(
            f"💰 {target.mention} tiene {format_money(user_data['money'])}.",
            ephemeral=True
        )

    @app_commands.command(name="daily", description="Reclama tu premio diario de gambling.")
    async def daily(self, interaction: discord.Interaction):
        data = load_data()
        user_data = get_user_data(data, interaction.guild_id, interaction.user.id)
        today = datetime.datetime.utcnow().date().isoformat()
        if user_data.get("daily_claimed") == today:
            await interaction.response.send_message(
                "❌ Ya has reclamado tu premio diario. Vuelve mañana.",
                ephemeral=True
            )
            return
        reward = 50
        user_data["money"] += reward
        user_data["daily_claimed"] = today
        save_data(data)
        await interaction.response.send_message(
            f"✅ ¡Premio diario reclamado! Has ganado {format_money(reward)}. Ahora tienes {format_money(user_data['money'])}.",
            ephemeral=True
        )

    @app_commands.command(name="bet", description="Apuesta una cantidad para ganar o perder.")
    @app_commands.describe(amount="Cantidad de monedas a apostar")
    async def bet(self, interaction: discord.Interaction, amount: int):
        if amount <= 0:
            await interaction.response.send_message(
                "❌ La cantidad debe ser un número positivo.",
                ephemeral=True
            )
            return
        data = load_data()
        user_data = get_user_data(data, interaction.guild_id, interaction.user.id)
        current_money = user_data.get("money", 100)
        if amount > current_money:
            await interaction.response.send_message(
                f"❌ No tienes suficientes monedas. Tu saldo es {format_money(current_money)}.",
                ephemeral=True
            )
            return

        win = random.choice([True, False])
        if win:
            user_data["money"] += amount
            embed = discord.Embed(
                title="🎉 Apuesta ganada",
                description=(
                    f"{interaction.user.mention} apostó {format_money(amount)} y ganó {format_money(amount)}.\n"
                    f"Saldo actual: {format_money(user_data['money'])}."
                ),
                color=discord.Color.green()
            )
        else:
            user_data["money"] = max(0, current_money - amount)
            embed = discord.Embed(
                title="😢 Apuesta perdida",
                description=(
                    f"{interaction.user.mention} apostó {format_money(amount)} y lo perdió.\n"
                    f"Saldo actual: {format_money(user_data['money'])}."
                ),
                color=discord.Color.red()
            )
        save_data(data)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Muestra el ranking de dinero en gambling.")
    async def leaderboard(self, interaction: discord.Interaction):
        data = load_data()
        top = get_top_balances(data, interaction.guild, limit=10)
        if not top:
            await interaction.response.send_message(
                "No hay datos de gambling aún.", ephemeral=True
            )
            return
        description = []
        for idx, (uid, balance) in enumerate(top, start=1):
            member = interaction.guild.get_member(int(uid))
            name = member.display_name if member else f"User {uid}"
            description.append(f"**{idx}.** {name} — `{format_money(balance)}`")
        embed = discord.Embed(
            title="🏅 Gambling Leaderboard",
            description="\n".join(description),
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Gambling(bot))
