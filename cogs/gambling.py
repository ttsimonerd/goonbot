import os
import json
import random
import asyncio
import datetime
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
    defaults = {"gambling_channel_id": None, "gambling_lockout_hours": 24, "gambling_max_warns": 3}
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
        data[gid][uid] = {"warns": 0, "locked_until": None}
    return data[gid][uid]


# ---------------------
# Cog
# ---------------------
class Gambling(commands.Cog, name="Gambling"):
    """Russian Roulette y sistema de warns para el canal de gambling."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

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

    @app_commands.command(name="roulette", description="¡Juega a la ruleta rusa! 1/6 de morir... 💀")
    async def roulette(self, interaction: discord.Interaction):
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
                # Lockout expired, reset
                user_data["warns"] = 0
                user_data["locked_until"] = None

        # Roll! 1 in 6 chance of dying
        outcome = random.randint(1, 6)
        died = (outcome == 1)

        if died:
            user_data["warns"] += 1
            warns = user_data["warns"]

            if warns >= MAX_WARNS:
                # Lock the channel
                locked_until_dt = datetime.datetime.utcnow() + datetime.timedelta(hours=LOCKOUT_HOURS)
                user_data["locked_until"] = locked_until_dt.isoformat()
                save_data(data)

                await self._lock_channel(interaction.guild, interaction.user)
                self.bot.loop.create_task(
                    self._unlock_channel(interaction.guild_id, interaction.user.id, LOCKOUT_HOURS)
                )

                embed = discord.Embed(
                    title="💀 MUERTO — BANEADO",
                    description=(
                        f"{interaction.user.mention} ha muerto en la ruleta rusa por **{warns}ª vez**.\n\n"
                        f"🔒 **Canal de gambling bloqueado por {LOCKOUT_HOURS} horas.** Rip bozo."
                    ),
                    color=discord.Color.dark_red()
                )
                embed.set_footer(text=f"Warns: {warns}/{MAX_WARNS} — Hasta la vista.")
            else:
                save_data(data)
                embed = discord.Embed(
                    title="💀 BANG — MUERTO",
                    description=(
                        f"{interaction.user.mention} intentó la ruleta rusa... y perdió. ☠️\n\n"
                        f"⚠️ **Warn {warns}/{MAX_WARNS}** — Un más y te banean del gambling."
                    ),
                    color=discord.Color.red()
                )
                embed.set_footer(text="Más vale que la próxima vez tengas más suerte.")
        else:
            save_data(data)
            survival_msgs = [
                "El tambor giró... y sobreviviste. Esta vez. 😏",
                "CLICK. Vacío. Tienes la suerte del diablo. 🍀",
                "Vive para jugar otro día. Por ahora. 😈",
                "El cañón apuntó... y falló. Eres un afortunado, nigga. 😂",
                "¡Superviviente! Por los pelos... 💪",
            ]
            embed = discord.Embed(
                title="✅ CLICK — SOBREVIVES",
                description=f"{interaction.user.mention} {random.choice(survival_msgs)}",
                color=discord.Color.green()
            )
            warns = user_data["warns"]
            if warns > 0:
                embed.set_footer(text=f"Warns actuales: {warns}/{MAX_WARNS}")

        await interaction.response.send_message(embed=embed)

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


async def setup(bot: commands.Bot):
    await bot.add_cog(Gambling(bot))
