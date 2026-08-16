import random
import asyncio
import datetime
import logging
import uuid
from collections import Counter

import discord
from discord import app_commands
from discord.ext import commands

import db

logger = logging.getLogger(__name__)


# ---------------------
# Pure helpers (no state) — unchanged from the original
# ---------------------
def format_money(amount: int) -> str:
    return f"{amount:,} coins"


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
        "Carta alta", "Pareja", "Doble pareja", "Trío", "Escalera",
        "Color", "Full", "Póker", "Escalera de color"
    ]
    return names[rank]


def roulette_wheel_display(wheel: int, color: str, choice: str) -> str:
    wheel_emoji = {"green": "🟢", "red": "🔴", "black": "⚫"}
    choice_emoji = {"green": "🟢", "red": "🔴", "black": "⚫", "even": "⚪", "odd": "⚫"}
    return (
        "🎡 — Bet: "
        f"{choice_emoji.get(choice, '🎯')} **{choice.upper()}**\n"
        "➡️ Result: "
        f"`{wheel}` {wheel_emoji.get(color, '❓')} ({color})\n"
        "```\n"
        " 0  1  2  3  4  5  6  7  8  9\n"
        "10 11 12 13 14 15 16 17 18 19\n"
        "20 21 22 23 24 25 26 27 28 29\n"
        "30 31 32 33 34 35 36\n"
        "```"
    )


def roulette_color(number: int) -> str:
    if number == 0:
        return "green"
    red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    return "red" if number in red_numbers else "black"


def predict_multiplier(days: int) -> float:
    return 1.0 + 0.15 * min(days, 20)


def predict_success_chance(days: int) -> float:
    return max(0.2, 0.85 - 0.03 * min(days, 20))


# ---------------------
# Cog
# ---------------------
class Gambling(commands.Cog, name="Gambling"):
    """Economía compartida y juegos de azar (ruleta, blackjack, póker, etc.)."""

    prediction_group = app_commands.Group(
        name="votebet",
        description="Poll bets"
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Arranca los bucles de fondo al cargar el cog."""
        self.bot.create_background_task(self._daily_winners_loop())
        self.bot.create_background_task(self._prediction_resolution_loop())
        self.bot.create_background_task(self._lockout_cleanup_loop())

    async def _get_gambling_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        settings = await db.get_settings(guild.id)
        ch_id = settings.get("gambling_channel_id")
        if ch_id:
            ch = guild.get_channel(ch_id)
            if ch:
                return ch
        for ch in guild.text_channels:
            if "gambling" in ch.name.lower():
                return ch
        return None

    async def _get_gambling_winners_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        settings = await db.get_settings(guild.id)
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

    async def _post_daily_winners(self) -> None:
        """Publica el ranking diario en el canal de ganadores."""
        for guild in self.bot.guilds:
            channel = await self._get_gambling_winners_channel(guild)
            if channel is None:
                continue
            top = await db.get_top_balances(guild.id, limit=5)
            if not top:
                continue
            lines = []
            for idx, (uid, balance) in enumerate(top, start=1):
                member = guild.get_member(int(uid))
                display = member.display_name if member else f"User {uid}"
                lines.append(f"**{idx}.** {display} — `{format_money(balance)}`")
            embed = discord.Embed(
                title="🏆 Daily Winners",
                description="\n".join(lines),
                color=discord.Color.gold(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text="Gambling Info")
            try:
                await channel.send(embed=embed)
            except Exception as e:
                logger.error("Failed to post daily winners in %s: %s", guild.name, e)

    async def _resolve_due_predictions(self) -> None:
        """Resuelve las apuestas (votebet) que ya han vencido."""
        now = datetime.datetime.utcnow()
        for guild in self.bot.guilds:
            predictions = await db.get_predictions(guild.id, include_settled=False)
            channel = await self._get_gambling_channel(guild) or await self._get_gambling_winners_channel(guild)
            for pred in predictions:
                resolve_at = datetime.datetime.fromisoformat(pred["resolve_at"])
                if now < resolve_at:
                    continue

                creator_id = int(pred["creator_id"])
                amount = pred["amount"]
                multiplier = pred["multiplier"]
                poll_channel = guild.get_channel(pred["channel_id"]) if pred["channel_id"] else None
                poll_message = None
                yes_votes = 0
                no_votes = 0
                poll_result = None
                if poll_channel and pred["message_id"]:
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
                    poll_basis = "No result."
                else:
                    success = poll_result
                    poll_basis = f"Result: ✅ {yes_votes} vs ❌ {no_votes}."

                member = guild.get_member(creator_id)
                mention = member.mention if member else f"<@{creator_id}>"
                if success:
                    payout = int(amount * multiplier)
                    await db.add_money(guild.id, creator_id, payout)
                    result_text = f"✅ {mention} won {format_money(payout)}."
                else:
                    result_text = f"❌ {mention} lost the vote bet."

                await db.update_prediction(
                    guild.id, pred["bet_id"], settled=1, result="win" if success else "lose"
                )

                if channel:
                    embed = discord.Embed(
                        title="📣 Bet results",
                        description=result_text,
                        color=discord.Color.blurple(),
                        timestamp=now
                    )
                    embed.add_field(name="Bet", value=pred["description"], inline=False)
                    embed.add_field(name="Votes", value=f"✅ {yes_votes} — ❌ {no_votes}", inline=True)
                    embed.add_field(name="Result", value="✅ Ganó" if success else "❌ Perdió", inline=True)
                    embed.add_field(name="Mult", value=f"x{multiplier:.2f}", inline=True)
                    embed.add_field(name="Base", value=poll_basis, inline=False)
                    try:
                        await channel.send(embed=embed)
                    except Exception as e:
                        logger.error("Failed to post prediction resolution in %s: %s", guild.name, e)

    async def _prediction_resolution_loop(self) -> None:
        """Bucle que resuelve predicciones cada 60s."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await self._resolve_due_predictions()
            await asyncio.sleep(60)

    async def _daily_winners_loop(self) -> None:
        """Bucle que publica ganadores a medianoche UTC."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.datetime.utcnow()
            tomorrow = now.date() + datetime.timedelta(days=1)
            next_run = datetime.datetime.combine(tomorrow, datetime.time(0, 0, 0))
            wait_seconds = (next_run - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            await self._post_daily_winners()

    async def _lock_channel(self, guild: discord.Guild, user: discord.Member) -> None:
        """Bloquea al usuario del canal de gambling."""
        settings = await db.get_settings(guild.id)
        max_warns = settings.get("gambling_max_warns", 3)
        ch = await self._get_gambling_channel(guild)
        if ch is None:
            return
        await ch.set_permissions(
            user, send_messages=False, reason=f"Gambling ban: {max_warns} warns reached."
        )

    async def _unlock_user(self, guild: discord.Guild, user_id: int) -> None:
        """Reset a user's gambling lockout: channel override + DB state.

        Idempotent, so it can be called from a command, the background
        unlock task, or the restart-recovery loop.
        """
        ch = await self._get_gambling_channel(guild)
        member = guild.get_member(user_id)
        if ch and member:
            await ch.set_permissions(member, send_messages=None, reason="Gambling ban expired.")
        await db.update_user(guild.id, user_id, warns=0, locked_until=None)

    async def _unlock_channel(self, guild_id: int, user_id: int, lockout_hours: int) -> None:
        """Desbloquea al usuario tras el tiempo de ban (tarea en segundo plano)."""
        await asyncio.sleep(lockout_hours * 3600)
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        await self._unlock_user(guild, user_id)

    async def _lockout_cleanup_loop(self) -> None:
        """Recupera bloqueos expirados tras un reinicio del bot."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._cleanup_expired_lockouts()
            except Exception as e:
                logger.error("Lockout cleanup error: %s", e)
            await asyncio.sleep(60)

    async def _cleanup_expired_lockouts(self) -> None:
        """Unlocks every user whose lockout timestamp has passed."""
        now = datetime.datetime.utcnow()
        for guild in self.bot.guilds:
            locked = await db.get_locked_users(guild.id)
            for user_id, locked_until in locked:
                try:
                    unlock_dt = datetime.datetime.fromisoformat(locked_until)
                except (ValueError, TypeError):
                    continue
                if now >= unlock_dt:
                    await self._unlock_user(guild, int(user_id))

    @app_commands.command(name="roulette", description="Bet on roulette")
    @app_commands.describe(bet="Bet", choice="red, black, even, odd, green o número (0-36)")
    async def roulette(self, interaction: discord.Interaction, bet: int, choice: str | None = None) -> None:
        """Juega a la ruleta apostando dinero."""
        settings = await db.get_settings(interaction.guild_id)
        LOCKOUT_HOURS = settings.get("gambling_lockout_hours", 24)
        MAX_WARNS = settings.get("gambling_max_warns", 3)

        user = await db.get_user(interaction.guild_id, interaction.user.id)
        locked_until = user["locked_until"]
        if locked_until:
            unlock_dt = datetime.datetime.fromisoformat(locked_until)
            if datetime.datetime.utcnow() < unlock_dt:
                remaining = unlock_dt - datetime.datetime.utcnow()
                hours, rem = divmod(int(remaining.total_seconds()), 3600)
                minutes = rem // 60
                await interaction.response.send_message(
                    f"🔒 You are banned from gambling for **{hours}h {minutes}m**. Son :sob:",
                    ephemeral=True
                )
                return
            else:
                await self._unlock_user(interaction.guild, interaction.user.id)
                user["warns"] = 0

        current_money = user["money"]
        if bet <= 0:
            await interaction.response.send_message("❌ Bet quantity incorrect.", ephemeral=True)
            return
        if bet > current_money:
            await interaction.response.send_message(
                f"❌ Broke boi. Your current money: {format_money(current_money)}.", ephemeral=True
            )
            return

        valid_choices = {"red", "black", "even", "odd", "green"}
        number_bet = None
        if choice:
            choice = choice.lower().strip()
            if choice.isdigit():
                number_bet = int(choice)
                if number_bet < 0 or number_bet > 36:
                    await interaction.response.send_message(
                        "❌ Invalid number. Use 0-36, or red, black, even, odd, green.",
                        ephemeral=True,
                    )
                    return
            elif choice not in valid_choices:
                await interaction.response.send_message(
                    "❌ Invalid option. Use red, black, even, odd, green o un número (0-36).",
                    ephemeral=True,
                )
                return
        else:
            choice = random.choice(["red", "black", "even", "odd"])

        wheel = random.randint(0, 36)
        color = roulette_color(wheel)
        win = False
        payout = 0
        choice_labels = {"red": "Rojo", "black": "Negro", "even": "Par", "odd": "Impar", "green": "Verde"}

        if number_bet is not None:
            win = (wheel == number_bet)
            payout = bet * 35
        elif choice == "green":
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

        bet_label = f"número **{number_bet}**" if number_bet is not None else f"**{choice_labels.get(choice, choice)}**"
        result_desc = (
            f"{interaction.user.mention} apostó {format_money(bet)} a {bet_label}.\n"
            f"{roulette_wheel_display(wheel, color, choice)}\n\n"
        )

        if win:
            new_balance = await db.add_money(interaction.guild_id, interaction.user.id, payout)
            result_title = "🎉 Win Win Win!"
            result_desc += f"You won {format_money(payout)}. Current money: {format_money(new_balance)}."
        else:
            new_balance = await db.add_money(interaction.guild_id, interaction.user.id, -bet)
            new_warns = user["warns"] + 1
            await db.update_user(interaction.guild_id, interaction.user.id, warns=new_warns)
            result_title = "💀 You lost... Lol"
            result_desc += f"You lost the bet. Current money: {format_money(new_balance)}."
            if new_warns >= MAX_WARNS:
                locked_until_dt = datetime.datetime.utcnow() + datetime.timedelta(hours=LOCKOUT_HOURS)
                await db.update_user(interaction.guild_id, interaction.user.id, locked_until=locked_until_dt.isoformat())
                await self._lock_channel(interaction.guild, interaction.user)
                self.bot.create_background_task(
                    self._unlock_channel(interaction.guild_id, interaction.user.id, LOCKOUT_HOURS)
                )
                result_desc += f"\n🔒 You have {new_warns} warns and got banned for {LOCKOUT_HOURS} hours."

        embed = discord.Embed(
            title=result_title, description=result_desc,
            color=discord.Color.green() if win else discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="blackjack", description="Blackjack.")
    @app_commands.describe(bet="Bet quantity")
    async def blackjack(self, interaction: discord.Interaction, bet: int) -> None:
        """Juega al blackjack contra la banca."""
        user = await db.get_user(interaction.guild_id, interaction.user.id)
        current_money = user["money"]

        if bet <= 0:
            await interaction.response.send_message("❌ Invalid bet quantity", ephemeral=True)
            return
        if bet > current_money:
            await interaction.response.send_message(
                f"❌ Broke boi. Current money: {format_money(current_money)}.", ephemeral=True
            )
            return

        await db.add_money(interaction.guild_id, interaction.user.id, -bet)

        deck = build_deck()
        random.shuffle(deck)
        user_cards = [deck.pop(), deck.pop()]
        dealer_cards = [deck.pop(), deck.pop()]
        guild_id = interaction.guild_id

        class BlackjackView(discord.ui.View):
            def __init__(self, author_id: int) -> None:
                super().__init__(timeout=120)
                self.author_id = author_id
                self.user_cards = user_cards
                self.dealer_cards = dealer_cards
                self.deck = deck

            def update_embed(self, embed: discord.Embed) -> discord.Embed:
                embed.clear_fields()
                embed.add_field(name="YOUR cards", value=" ".join(self.user_cards), inline=False)
                embed.add_field(name="DEALER cards", value=f"{self.dealer_cards[0]} ??", inline=False)
                total = best_blackjack_total(self.user_cards)
                embed.set_footer(text=f"Total: {total}")
                return embed

            async def finish(self, interaction: discord.Interaction, result_title: str, description: str, win: bool) -> None:
                for child in self.children:
                    child.disabled = True
                self.stop()
                embed = discord.Embed(title=result_title, description=description, color=discord.Color.green() if win else discord.Color.red())
                embed.add_field(name="Tus cartas", value=" ".join(self.user_cards), inline=False)
                embed.add_field(name="Cartas del dealer", value=" ".join(self.dealer_cards), inline=False)
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
            async def hit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("Ts isn't you game nih.", ephemeral=True)
                    return
                self.user_cards.append(self.deck.pop())
                total = best_blackjack_total(self.user_cards)
                if total > 21:
                    await self.finish(interaction, "💥 Busted", f"You lost and ur total is: {total}.", False)
                    return
                embed = discord.Embed(title="Blackjack", description="Hit or Stand")
                await interaction.response.edit_message(embed=self.update_embed(embed), view=self)

            @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
            async def stand(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("Ts isn't you game nih.", ephemeral=True)
                    return
                dealer_total = best_blackjack_total(self.dealer_cards)
                while dealer_total < 17:
                    self.dealer_cards.append(self.deck.pop())
                    dealer_total = best_blackjack_total(self.dealer_cards)
                user_total = best_blackjack_total(self.user_cards)
                if dealer_total > 21 or user_total > dealer_total:
                    winnings = int(bet * 2)
                    await db.add_money(guild_id, interaction.user.id, winnings)
                    await self.finish(interaction, "🎉 Win Win Win!", f"You: {user_total}. Dealer: {dealer_total}. You won {format_money(winnings)}.", True)
                elif user_total == dealer_total:
                    # Push — devuelve la apuesta original.
                    await db.add_money(guild_id, interaction.user.id, bet)
                    await self.finish(interaction, "🤝 Push", f"You: {user_total}. Dealer: {dealer_total}. Empate — se te devuelve la apuesta.", True)
                else:
                    await self.finish(interaction, "😢 You lost...", f"You: {user_total}. Dealer: {dealer_total}. You loose!", False)

        view = BlackjackView(interaction.user.id)
        embed = discord.Embed(title="Blackjack", description="Initial cards.", color=discord.Color.blurple())
        embed = view.update_embed(embed)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="poker", description="Play poker with the bot.")
    @app_commands.describe(bet="Bet quantity")
    async def poker(self, interaction: discord.Interaction, bet: int) -> None:
        """Juega una mano de póker rápida contra la banca."""
        user = await db.get_user(interaction.guild_id, interaction.user.id)
        current_money = user["money"]

        if bet <= 0:
            await interaction.response.send_message("❌ Invalid bet quantity.", ephemeral=True)
            return
        if bet > current_money:
            await interaction.response.send_message(
                f"❌ Broke boi :sob: . Your currency: {format_money(current_money)}.", ephemeral=True
            )
            return

        await db.add_money(interaction.guild_id, interaction.user.id, -bet)

        deck = build_deck()
        random.shuffle(deck)
        user_cards = [deck.pop() for _ in range(5)]
        dealer_cards = [deck.pop() for _ in range(5)]
        user_rank, user_tiebreak = poker_rank(user_cards)
        dealer_rank, dealer_tiebreak = poker_rank(dealer_cards)

        win = False
        result = "Tie"
        if user_rank > dealer_rank or (user_rank == dealer_rank and user_tiebreak > dealer_tiebreak):
            result = "Win"
            win = True
        elif user_rank < dealer_rank or (user_rank == dealer_rank and user_tiebreak < dealer_tiebreak):
            result = "Lost"
        else:
            result = "Tie"
            await db.add_money(interaction.guild_id, interaction.user.id, bet)

        if win:
            payout = int(bet * 2.5)
            await db.add_money(interaction.guild_id, interaction.user.id, payout)
            result_text = f"You win: {format_money(payout)}."
        elif result == "Tie":
            result_text = "Tie, nobody wins"
        else:
            result_text = "You lose!"

        embed = discord.Embed(title="Poker", color=discord.Color.purple())
        embed.add_field(name="You", value=" ".join(user_cards), inline=False)
        embed.add_field(name="Bot", value=" ".join(dealer_cards), inline=False)
        embed.add_field(name="Result", value=f"{result} — {hand_rank_name(user_rank)} vs {hand_rank_name(dealer_rank)}", inline=False)
        embed.add_field(name="Detail", value=result_text, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="crash", description="Double it or nah.")
    @app_commands.describe(bet="Bet")
    async def balatro(self, interaction: discord.Interaction, bet: int) -> None:
        """Juego crash: continúa para subir el multiplicador o cobra."""
        user = await db.get_user(interaction.guild_id, interaction.user.id)
        current_money = user["money"]

        if bet <= 0:
            await interaction.response.send_message("❌ Invalid bet quantity", ephemeral=True)
            return
        if bet > current_money:
            await interaction.response.send_message(
                f"❌ Broke boi. Your money: {format_money(current_money)}.", ephemeral=True
            )
            return

        await db.add_money(interaction.guild_id, interaction.user.id, -bet)
        guild_id = interaction.guild_id

        class BalatroView(discord.ui.View):
            def __init__(self, author_id: int, round_number: int = 1, multiplier: float = 1.25) -> None:
                super().__init__(timeout=120)
                self.author_id = author_id
                self.round_number = round_number
                self.multiplier = multiplier
                self.bet = bet

            def get_success_chance(self) -> float:
                return max(0.15, 0.75 - 0.10 * (self.round_number - 1))

            def get_reward(self) -> int:
                return int(self.bet * self.multiplier)

            def update_embed(self) -> discord.Embed:
                chance = int(self.get_success_chance() * 100)
                embed = discord.Embed(
                    title="Crash 🚀",
                    description=(
                        "Crash game: The mult keeps going up if you continue, but watch out not to crash!\n"
                        "Risk it continuing or save your money now"
                    ),
                    color=discord.Color.gold()
                )
                embed.add_field(name="Round", value=str(self.round_number), inline=True)
                embed.add_field(name="Chance", value=f"{chance}%", inline=True)
                embed.add_field(name="Multiplier", value=f"x{self.multiplier:.2f}", inline=True)
                embed.add_field(name="Current reward", value=format_money(self.get_reward()), inline=False)
                embed.set_footer(text="Risk keeps growing every round...")
                return embed

            async def finish(self, interaction: discord.Interaction, success: bool, text: str) -> None:
                for child in self.children:
                    child.disabled = True
                self.stop()
                if success:
                    payout = self.get_reward()
                    await db.add_money(guild_id, interaction.user.id, payout)
                    embed = discord.Embed(title="🏆 Saved money", description=text, color=discord.Color.green())
                    embed.add_field(name="Total:", value=format_money(payout), inline=False)
                else:
                    embed = discord.Embed(title="💥 You crashed!", description=text, color=discord.Color.red())
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary)
            async def continue_round(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("Ts isn't you game nih.", ephemeral=True)
                    return
                chance = self.get_success_chance()
                if random.random() < chance:
                    self.round_number += 1
                    self.multiplier += random.uniform(0.4, 0.85)
                    await interaction.response.edit_message(embed=self.update_embed(), view=self)
                else:
                    await self.finish(interaction, False, f"Lol, you crashed {self.round_number}.")

            @discord.ui.button(label="Stop", style=discord.ButtonStyle.success)
            async def cash_out(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("Ts isn't you game nih.", ephemeral=True)
                    return
                await self.finish(interaction, True, f"You stopped after {self.round_number} rounds and won: {format_money(self.get_reward())}.")

        view = BalatroView(interaction.user.id)
        await interaction.response.send_message(embed=view.update_embed(), view=view)

    @prediction_group.command(name="create", description="Create custom poll bet")
    @app_commands.describe(
        days="Days to go",
        amount="Inicial bet",
        prediction_description="Description to show"
    )
    async def create_prediction(self, interaction: discord.Interaction, days: int, amount: int, prediction_description: str) -> None:
        """Crea una apuesta personalizada (poll bet)."""
        if amount <= 0:
            await interaction.response.send_message("❌ Invalid bet.", ephemeral=True)
            return
        if days < 1 or days > 30:
            await interaction.response.send_message("❌ Days must be between 1 and 30.", ephemeral=True)
            return

        user = await db.get_user(interaction.guild_id, interaction.user.id)
        if amount > user["money"]:
            await interaction.response.send_message(
                f"❌ Broke boi. You currently have: {format_money(user['money'])}.", ephemeral=True
            )
            return

        await db.add_money(interaction.guild_id, interaction.user.id, -amount)
        bet_id = str(uuid.uuid4())[:8]
        multiplier = predict_multiplier(days)
        created_at = datetime.datetime.utcnow()
        resolve_at = created_at + datetime.timedelta(days=days)

        await db.create_prediction(
            interaction.guild_id, bet_id,
            creator_id=str(interaction.user.id),
            description=prediction_description,
            amount=amount,
            days=days,
            created_at=created_at.isoformat(),
            resolve_at=resolve_at.isoformat(),
            multiplier=multiplier,
            success_chance=predict_success_chance(days),
            settled=0,
            result=None,
            channel_id=None,
            message_id=None,
        )

        poll_channel = await self._get_gambling_channel(interaction.guild) or interaction.channel
        if poll_channel is None:
            await interaction.response.send_message("❌ There isn't a channel to do this.", ephemeral=True)
            return

        poll_embed = discord.Embed(
            title="🗳️ New bet",
            description=prediction_description,
            color=discord.Color.blue(),
            timestamp=created_at
        )
        poll_embed.add_field(name="ID", value=bet_id, inline=True)
        poll_embed.add_field(name="Creator", value=interaction.user.mention, inline=True)
        poll_embed.add_field(name="Bet", value=format_money(amount), inline=True)
        poll_embed.add_field(name="Days to go", value=str(days), inline=True)
        poll_embed.add_field(name="Ends in", value=f"<t:{int(resolve_at.timestamp())}:F>", inline=False)
        poll_embed.add_field(name="Multiplier", value=f"x{multiplier:.2f}", inline=True)
        poll_embed.add_field(name="Votes", value="✅ Sí / ❌ No", inline=False)
        poll_embed.set_footer(text="Vote!")

        try:
            poll_message = await poll_channel.send(embed=poll_embed)
            await poll_message.add_reaction("✅")
            await poll_message.add_reaction("❌")
        except Exception as e:
            await db.add_money(interaction.guild_id, interaction.user.id, amount)
            await interaction.response.send_message(f"❌ Bet couldn't be created: {e}", ephemeral=True)
            return

        await db.update_prediction(
            interaction.guild_id, bet_id,
            channel_id=str(poll_channel.id), message_id=str(poll_message.id)
        )

        embed = discord.Embed(title="📈 Bet created!", description=prediction_description, color=discord.Color.blue())
        embed.add_field(name="ID", value=bet_id, inline=True)
        embed.add_field(name="Bet", value=format_money(amount), inline=True)
        embed.add_field(name="Days to go", value=str(days), inline=True)
        embed.add_field(name="Multiplier", value=f"x{multiplier:.2f}", inline=True)
        embed.add_field(name="Probability", value=f"{predict_success_chance(days) * 100:.0f}%", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @prediction_group.command(name="status", description="Check you active polls.")
    async def prediction_status(self, interaction: discord.Interaction) -> None:
        """Consulta tus apuestas activas."""
        predictions = await db.get_predictions(interaction.guild_id, include_settled=False)
        lines = []
        for pred in predictions:
            if pred["creator_id"] != str(interaction.user.id):
                continue
            resolve_at = datetime.datetime.fromisoformat(pred["resolve_at"])
            remaining = resolve_at - datetime.datetime.utcnow()
            hours = max(0, int(remaining.total_seconds() // 3600))
            minutes = max(0, int((remaining.total_seconds() % 3600) // 60))
            lines.append(f"**{pred['bet_id']}** — {pred['description']} — {format_money(pred['amount'])} — resolves in {hours}h {minutes}m")
        if not lines:
            await interaction.response.send_message("You have no active bets.", ephemeral=True)
            return
        embed = discord.Embed(title="📊 Active bets", description="\n".join(lines), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gambling_warns", description="Check warns.")
    @app_commands.describe(user="Target user")
    async def gambling_warns(self, interaction: discord.Interaction, user: discord.Member = None) -> None:
        """Consulta los warns de gambling de un usuario."""
        settings = await db.get_settings(interaction.guild_id)
        MAX_WARNS = settings.get("gambling_max_warns", 3)

        target = user or interaction.user
        target_data = await db.get_user(interaction.guild_id, target.id)
        warns = target_data["warns"]
        locked_until = target_data["locked_until"]

        embed = discord.Embed(title=f"📋 {target.display_name}'s Warns", color=discord.Color.orange())
        embed.add_field(name="Warns", value=f"{warns}/{MAX_WARNS}", inline=True)
        if locked_until:
            unlock_dt = datetime.datetime.fromisoformat(locked_until)
            if datetime.datetime.utcnow() < unlock_dt:
                embed.add_field(name="Status", value=f"🔒 Banned till <t:{int(unlock_dt.timestamp())}:R>", inline=True)
            else:
                embed.add_field(name="Status", value="✅ Good", inline=True)
        else:
            embed.add_field(name="Status", value="✅ Good", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gambling_pardon", description="[ADMIN]")
    @app_commands.describe(user="Target user")
    @app_commands.default_permissions(administrator=True)
    async def gambling_pardon(self, interaction: discord.Interaction, user: discord.Member) -> None:
        """Quita los warns de un usuario (admin)."""
        await db.update_user(interaction.guild_id, user.id, warns=0, locked_until=None)

        ch = await self._get_gambling_channel(interaction.guild)
        if ch:
            await ch.set_permissions(user, send_messages=None, reason="Admin pardon.")

        await interaction.response.send_message(
            f"✅ {user.mention} just got his warns removed!", ephemeral=True
        )

    @app_commands.command(name="balance", description="Check your balance")
    @app_commands.describe(user="User")
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None) -> None:
        """Muestra el saldo de un usuario."""
        target = user or interaction.user
        target_data = await db.get_user(interaction.guild_id, target.id)
        await interaction.response.send_message(
            f"💰 {target.mention} has {format_money(target_data['money'])}.", ephemeral=True
        )

    @app_commands.command(name="daily", description="Daily money reward")
    async def daily(self, interaction: discord.Interaction) -> None:
        """Reclama la recompensa diaria, con bonus por racha de días consecutivos."""
        user = await db.get_user(interaction.guild_id, interaction.user.id)
        today = datetime.datetime.utcnow().date()
        if user["daily_claimed"] == today.isoformat():
            await interaction.response.send_message("❌ You already claimed the daily reward.", ephemeral=True)
            return

        yesterday = (today - datetime.timedelta(days=1)).isoformat()
        streak = (user["daily_streak"] + 1) if user["daily_claimed"] == yesterday else 1

        base = random.randint(25, 100)
        bonus = min(streak - 1, 7) * 10
        reward = base + bonus

        new_balance = await db.add_money(interaction.guild_id, interaction.user.id, reward)
        await db.update_user(
            interaction.guild_id,
            interaction.user.id,
            daily_claimed=today.isoformat(),
            daily_streak=streak,
        )

        streak_text = f" 🔥 Racha: {streak} días" + (f" (+{bonus} bonus)" if bonus else "")
        await interaction.response.send_message(
            f"✅ ¡Daily reward redeemed! Won: {format_money(reward)}.{streak_text}\n"
            f"Current money: {format_money(new_balance)}.",
            ephemeral=True,
        )

    @app_commands.command(name="bet", description="Double your bet or not")
    @app_commands.describe(amount="Bet quantity")
    async def bet(self, interaction: discord.Interaction, amount: int) -> None:
        """Dobla tu apuesta o piérdela."""
        if amount <= 0:
            await interaction.response.send_message("❌ Invalid bet quantity", ephemeral=True)
            return
        user = await db.get_user(interaction.guild_id, interaction.user.id)
        current_money = user["money"]
        if amount > current_money:
            await interaction.response.send_message(
                f"❌ Broke boi. You currently have: {format_money(current_money)}.", ephemeral=True
            )
            return

        win = random.choice([True, False])
        if win:
            new_balance = await db.add_money(interaction.guild_id, interaction.user.id, amount)
            embed = discord.Embed(
                title="🎉 Win Win Win!",
                description=(
                    f"{interaction.user.mention} bid {format_money(amount)} and won {format_money(amount)}.\n"
                    f"Current money: {format_money(new_balance)}."
                ),
                color=discord.Color.green()
            )
        else:
            new_balance = await db.add_money(interaction.guild_id, interaction.user.id, -amount)
            embed = discord.Embed(
                title="😢 You lose",
                description=(
                    f"{interaction.user.mention} bid {format_money(amount)} and lost.\n"
                    f"Current money: {format_money(new_balance)}."
                ),
                color=discord.Color.red()
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Gambling leaderboard.")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        """Muestra el ranking de dinero."""
        top = await db.get_top_balances(interaction.guild_id, limit=10)
        if not top:
            await interaction.response.send_message("There is no data.", ephemeral=True)
            return
        description = []
        for idx, (uid, balance) in enumerate(top, start=1):
            member = interaction.guild.get_member(int(uid))
            name = member.display_name if member else f"User {uid}"
            description.append(f"**{idx}.** {name} — `{format_money(balance)}`")
        embed = discord.Embed(title="🏅 Gambling Leaderboard", description="\n".join(description), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Gambling(bot))
