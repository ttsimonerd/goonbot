"""
GoonBot music collection and battle system.

Commands:
  /music add <url>        Add a song to your collection.
  /music history          Show recent battles.
  /music info <url>       Show song ownership/ELO.
  /music battle            Start a normal battle between two songs.
  /music reclaim <url>    Challenge the current owner of a song.

The cog keeps its own migration-safe music tables so it can be dropped into
an existing GoonBot installation without requiring a manual SQLite migration.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import random
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

import db


NORMAL_COOLDOWN = 60
RECLAIM_COOLDOWN = 60 * 60 * 24 * 3
INITIAL_ELO = 1000
WIN_GAIN_FRACTION = 0.50
LOSS_FRACTION = 0.25


def now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat()


def normalize_url(url: str) -> str:
    url = url.strip()
    # Keep a stable enough URL for duplicate detection while removing
    # common tracking parameters.
    if "youtube.com/watch" in url:
        try:
            from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
            p = urlparse(url)
            q = parse_qs(p.query)
            if "v" in q:
                return urlunparse((p.scheme, p.netloc, p.path, "", urlencode({"v": q["v"][0]}), ""))
        except Exception:
            pass
    return url.rstrip("/")


async def extract_song(url: str) -> tuple[str, str, str]:
    loop = asyncio.get_running_loop()

    def _extract():
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("track") or info.get("title") or "Unknown title"
            artist = info.get("artist") or info.get("uploader") or info.get("channel") or "Unknown artist"
            webpage = info.get("webpage_url") or url
            return title, artist, webpage

    return await loop.run_in_executor(None, _extract)


class MusicBattleView(discord.ui.View):
    """Vista de botones para votar en una batalla musical normal."""

    def __init__(self, cog: "Music", battle_id: int, song_a: int, song_b: int) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.battle_id = battle_id
        self.song_a = song_a
        self.song_b = song_b
        self.votes: dict[int, int] = {}
        self.message: Optional[discord.Message] = None

    async def vote(self, interaction: discord.Interaction, song_id: int) -> None:
        if interaction.user.bot:
            return
        self.votes[interaction.user.id] = song_id
        await interaction.response.send_message("Voto registrado.", ephemeral=True)

        a = sum(v == self.song_a for v in self.votes.values())
        b = sum(v == self.song_b for v in self.votes.values())

        if a + b >= 3:
            await self.finish(interaction.channel, a, b)

    async def finish(self, channel: Optional[discord.abc.Messageable], a: int, b: int) -> None:
        if self.message is None:
            return
        winner = self.song_a if a > b else self.song_b if b > a else random.choice([self.song_a, self.song_b])
        await self.cog.finish_battle(self.battle_id, winner, a, b, special=False)
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass
        if channel:
            await channel.send(f"**Batalla terminada:** ganó la canción con ID `{winner}`.")


class ReclaimView(discord.ui.View):
    """Vista de botones para votar en una batalla especial de recuperación."""

    def __init__(self, cog: "Music", battle_id: int, challenger_song: int, target_song: int) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.battle_id = battle_id
        self.challenger_song = challenger_song
        self.target_song = target_song
        self.votes: dict[int, int] = {}
        self.message: Optional[discord.Message] = None

    async def vote(self, interaction: discord.Interaction, song_id: int) -> None:
        self.votes[interaction.user.id] = song_id
        await interaction.response.send_message("Voto registrado.", ephemeral=True)
        a = sum(v == self.challenger_song for v in self.votes.values())
        b = sum(v == self.target_song for v in self.votes.values())
        if a + b >= 5:
            await self.finish(interaction.channel, a, b)

    async def finish(self, channel: Optional[discord.abc.Messageable], a: int, b: int) -> None:
        if self.message is None:
            return
        winner = self.challenger_song if a > b else self.target_song if b > a else random.choice([self.challenger_song, self.target_song])
        await self.cog.finish_battle(self.battle_id, winner, a, b, special=True)
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass
        if channel:
            await channel.send("**Batalla especial terminada.** La canción se queda con su propietario actual salvo que el retador haya ganado.")


class Music(commands.GroupCog, group_name="music", description="Colección de canciones y batallas"):
    """Colección de canciones, propiedad y sistema de batallas musicales."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._schema_ready = False
        self._cooldowns: dict[tuple[int, int, str], float] = {}

    async def cog_load(self) -> None:
        """Prepara el esquema de la base de datos al cargar."""
        await self.ensure_schema()

    async def ensure_schema(self) -> None:
        """Crea las tablas de música si no existen."""
        if self._schema_ready:
            return
        conn = db._conn()
        await conn.executescript("""
        CREATE TABLE IF NOT EXISTS music_songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            url TEXT NOT NULL,
            normalized_url TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT 'unknown',
            owner_id TEXT NOT NULL,
            is_original INTEGER NOT NULL DEFAULT 0,
            elo INTEGER NOT NULL DEFAULT 1000,
            peak_elo INTEGER NOT NULL DEFAULT 1000,
            created_at TEXT NOT NULL,
            deleted_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_music_songs_guild_url
            ON music_songs(guild_id, normalized_url);

        CREATE TABLE IF NOT EXISTS music_battles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            song_a_id INTEGER NOT NULL,
            song_b_id INTEGER NOT NULL,
            battle_type TEXT NOT NULL DEFAULT 'normal',
            started_at TEXT NOT NULL,
            ended_at TEXT,
            winner_song_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            channel_id TEXT,
            message_id TEXT
        );

        CREATE TABLE IF NOT EXISTS music_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            battle_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            song_id INTEGER NOT NULL,
            voted_at TEXT NOT NULL,
            UNIQUE(battle_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS music_ownership (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            song_id INTEGER NOT NULL,
            owner_id TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            lost_at TEXT
        );

        CREATE TABLE IF NOT EXISTS music_cooldowns (
            guild_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            cooldown_type TEXT NOT NULL,
            available_at TEXT NOT NULL,
            PRIMARY KEY(guild_id, user_id, cooldown_type)
        );
        """)
        await conn.commit()
        self._schema_ready = True

    async def song_by_id(self, guild_id: int, song_id: int) -> tuple | None:
        cur = await db._conn().execute(
            "SELECT id,title,artist,url,owner_id,elo,peak_elo,created_at FROM music_songs "
            "WHERE guild_id=? AND id=? AND deleted_at IS NULL",
            (str(guild_id), song_id),
        )
        return await cur.fetchone()

    async def song_by_url(self, guild_id: int, url: str) -> tuple | None:
        cur = await db._conn().execute(
            "SELECT id,title,artist,url,owner_id,elo,peak_elo,created_at FROM music_songs "
            "WHERE guild_id=? AND normalized_url=? AND deleted_at IS NULL",
            (str(guild_id), normalize_url(url)),
        )
        return await cur.fetchone()

    async def owner_song(self, guild_id: int, owner_id: int) -> tuple | None:
        cur = await db._conn().execute(
            "SELECT id,title,artist,url,owner_id,elo FROM music_songs "
            "WHERE guild_id=? AND owner_id=? AND deleted_at IS NULL ORDER BY elo DESC LIMIT 1",
            (str(guild_id), str(owner_id)),
        )
        return await cur.fetchone()

    async def cooldown_remaining(self, guild_id: int, user_id: int, kind: str) -> int:
        cur = await db._conn().execute(
            "SELECT available_at FROM music_cooldowns WHERE guild_id=? AND user_id=? AND cooldown_type=?",
            (str(guild_id), str(user_id), kind),
        )
        row = await cur.fetchone()
        if not row:
            return 0
        try:
            left = int(dt.datetime.fromisoformat(row[0]).timestamp() - time.time())
            return max(0, left)
        except Exception:
            return 0

    async def set_cooldown(self, guild_id: int, user_id: int, kind: str, seconds: int) -> None:
        available = dt.datetime.utcnow() + dt.timedelta(seconds=seconds)
        async with db._write_lock:
            await db._conn().execute(
                "INSERT INTO music_cooldowns(guild_id,user_id,cooldown_type,available_at) VALUES(?,?,?,?) "
                "ON CONFLICT(guild_id,user_id,cooldown_type) DO UPDATE SET available_at=excluded.available_at",
                (str(guild_id), str(user_id), kind, available.replace(microsecond=0).isoformat()),
            )
            await db._conn().commit()

    @app_commands.command(name="add", description="Añade una canción y te la adjudica.")
    @app_commands.describe(url="URL de YouTube u otra plataforma compatible")
    async def add(self, interaction: discord.Interaction, url: str) -> None:
        """Añade una canción y te la adjudica."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Este comando solo funciona dentro de un servidor.", ephemeral=True)
            return
        existing = await self.song_by_url(interaction.guild_id, url)
        if existing:
            await interaction.followup.send(
                f"**Duplicada.** Esta canción ya está adjudicada a <@{existing[4]}>.\n"
                "Puedes usar `/music reclaim` para intentar recuperarla mediante una batalla especial.",
                ephemeral=True,
            )
            return

        try:
            title, artist, final_url = await extract_song(url)
        except Exception as exc:
            await interaction.followup.send(f"No he podido obtener la canción: `{exc}`", ephemeral=True)
            return

        norm = normalize_url(final_url)
        if await self.song_by_url(interaction.guild_id, norm):
            existing = await self.song_by_url(interaction.guild_id, norm)
            await interaction.followup.send(
                f"**Duplicada.** Ya pertenece a <@{existing[4]}>.",
                ephemeral=True,
            )
            return

        platform = "youtube" if "youtube.com" in final_url or "youtu.be" in final_url else "other"
        async with db._write_lock:
            cur = await db._conn().execute(
                "INSERT INTO music_songs(guild_id,title,artist,url,normalized_url,platform,owner_id,is_original,elo,peak_elo,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (str(interaction.guild_id), title, artist, final_url, norm, platform,
                 str(interaction.user.id), 0, INITIAL_ELO, INITIAL_ELO, now_iso()),
            )
            song_id = cur.lastrowid
            await db._conn().execute(
                "INSERT INTO music_ownership(guild_id,song_id,owner_id,acquired_at) VALUES(?,?,?,?)",
                (str(interaction.guild_id), song_id, str(interaction.user.id), now_iso()),
            )
            await db._conn().commit()

        embed = discord.Embed(
            title="Canción adjudicada",
            description=f"**{title}**\n{artist}",
        )
        embed.add_field(name="Propietario", value=interaction.user.mention)
        embed.add_field(name="ELO", value=str(INITIAL_ELO))
        embed.add_field(name="Información", value="Esta canción queda asociada a ti hasta que pierdas una batalla especial.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="history", description="Muestra el historial de batallas musicales.")
    async def history(self, interaction: discord.Interaction) -> None:
        """Muestra el historial de batallas musicales."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Solo disponible en servidores.", ephemeral=True)
            return
        cur = await db._conn().execute(
            "SELECT mb.id, mb.battle_type, mb.started_at, mb.winner_song_id, "
            "mb.song_a_id, mb.song_b_id, "
            "a.title, a.artist, a.owner_id, b.title, b.artist, b.owner_id "
            "FROM music_battles mb JOIN music_songs a ON a.id=mb.song_a_id "
            "JOIN music_songs b ON b.id=mb.song_b_id "
            "WHERE mb.guild_id=? AND mb.status='finished' ORDER BY mb.id DESC LIMIT 10",
            (str(interaction.guild_id),),
        )
        rows = await cur.fetchall()
        embed = discord.Embed(title="Historial de batallas musicales")
        if not rows:
            embed.description = "Todavía no hay batallas."
        else:
            lines = []
            for r in rows:
                winner_id = r[3]
                song_a_id = r[4]
                song_b_id = r[5]
                title_a = r[6]
                title_b = r[9]
                if winner_id == song_a_id:
                    winner_title = title_a
                elif winner_id == song_b_id:
                    winner_title = title_b
                else:
                    winner_title = "Empate"
                icon = "⚔️" if r[1] == "normal" else "👑"
                lines.append(f"{icon} **#{r[0]}** — {title_a} vs {title_b} → **{winner_title}**")
            embed.description = "\n".join(lines)
        embed.set_footer(text="Últimas 10 batallas")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _song_id_by_title_pair(self, guild_id: int, title: str, artist: str) -> int | None:
        cur = await db._conn().execute(
            "SELECT id FROM music_songs WHERE guild_id=? AND title=? AND artist=? LIMIT 1",
            (str(guild_id), title, artist),
        )
        row = await cur.fetchone()
        return row[0] if row else None

    @app_commands.command(name="info", description="Muestra la información y propietario de una canción.")
    @app_commands.describe(url="URL de la canción")
    async def info(self, interaction: discord.Interaction, url: str) -> None:
        """Muestra la información y propietario de una canción."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Solo disponible en servidores.", ephemeral=True)
            return
        song = await self.song_by_url(interaction.guild_id, url)
        if not song:
            await interaction.followup.send("Esa canción todavía no está adjudicada.", ephemeral=True)
            return
        embed = discord.Embed(title=song[1], description=song[2], url=song[3])
        embed.add_field(name="Propietario", value=f"<@{song[4]}>")
        embed.add_field(name="ELO", value=str(song[5]))
        embed.add_field(name="ELO máximo", value=str(song[6]))
        embed.add_field(name="Cómo recuperarla", value="Usa `/music reclaim` para desafiar al propietario.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="battle", description="Inicia una batalla musical normal.")
    async def battle(self, interaction: discord.Interaction) -> None:
        """Inicia una batalla musical normal entre dos canciones."""
        await interaction.response.defer()
        if interaction.guild_id is None:
            await interaction.followup.send("Solo disponible en servidores.")
            return
        left = await self.cooldown_remaining(interaction.guild_id, interaction.user.id, "normal")
        if left:
            await interaction.followup.send(f"Tienes que esperar {left // 60} min {left % 60} s para otra batalla.")
            return

        cur = await db._conn().execute(
            "SELECT id,title,artist,owner_id,elo FROM music_songs WHERE guild_id=? AND deleted_at IS NULL "
            "ORDER BY RANDOM() LIMIT 2",
            (str(interaction.guild_id),),
        )
        songs = await cur.fetchall()
        if len(songs) < 2:
            await interaction.followup.send("Necesito al menos dos canciones adjudicadas.")
            return

        a, b = songs
        async with db._write_lock:
            cur = await db._conn().execute(
                "INSERT INTO music_battles(guild_id,song_a_id,song_b_id,battle_type,started_at,channel_id,status) "
                "VALUES(?,?,?,?,?,?,?)",
                (str(interaction.guild_id), a[0], b[0], "normal", now_iso(), str(interaction.channel_id), "pending"),
            )
            battle_id = cur.lastrowid
            await db._conn().commit()
        await self.set_cooldown(interaction.guild_id, interaction.user.id, "normal", NORMAL_COOLDOWN)

        embed = self.battle_embed("⚔️ Batalla musical", a, b, special=False)
        view = MusicBattleView(self, battle_id, a[0], b[0])
        view.add_item(discord.ui.Button(label=a[1][:80], style=discord.ButtonStyle.primary, custom_id=f"music:a:{battle_id}"))
        view.add_item(discord.ui.Button(label=b[1][:80], style=discord.ButtonStyle.secondary, custom_id=f"music:b:{battle_id}"))
        # Bind callbacks after construction because discord.py Buttons cannot
        # carry arbitrary coroutine arguments by themselves.
        view.children[0].callback = lambda i: view.vote(i, a[0])
        view.children[1].callback = lambda i: view.vote(i, b[0])
        view.message = await interaction.followup.send(embed=embed, view=view, wait=True)

    @app_commands.command(name="reclaim", description="Desafía al propietario de una canción para intentar recuperarla.")
    @app_commands.describe(url="URL de la canción que quieres recuperar")
    async def reclaim(self, interaction: discord.Interaction, url: str) -> None:
        """Desafía al propietario de una canción en una batalla especial."""
        await interaction.response.defer()
        if interaction.guild_id is None:
            await interaction.followup.send("Solo disponible en servidores.")
            return
        left = await self.cooldown_remaining(interaction.guild_id, interaction.user.id, "reclaim")
        if left:
            days = left // 86400
            hours = (left % 86400) // 3600
            await interaction.followup.send(f"Tu próxima batalla especial estará disponible en {days}d {hours}h.")
            return

        target = await self.song_by_url(interaction.guild_id, url)
        if not target:
            await interaction.followup.send("Esa canción no está adjudicada.")
            return
        if int(target[4]) == interaction.user.id:
            await interaction.followup.send("Ya eres el propietario de esa canción.")
            return

        challenger = await self.owner_song(interaction.guild_id, interaction.user.id)
        if not challenger:
            await interaction.followup.send("Necesitas tener al menos una canción adjudicada para desafiar.")
            return

        async with db._write_lock:
            cur = await db._conn().execute(
                "INSERT INTO music_battles(guild_id,song_a_id,song_b_id,battle_type,started_at,channel_id,status) "
                "VALUES(?,?,?,?,?,?,?)",
                (str(interaction.guild_id), challenger[0], target[0], "reclaim", now_iso(), str(interaction.channel_id), "pending"),
            )
            battle_id = cur.lastrowid
            await db._conn().commit()
        await self.set_cooldown(interaction.guild_id, interaction.user.id, "reclaim", RECLAIM_COOLDOWN)

        # battle_embed() expects rows shaped like (id, title, artist, owner_id, elo),
        # but owner_song()/song_by_url() return extra columns, so trim them here.
        challenger_view = (challenger[0], challenger[1], challenger[2], challenger[4], challenger[5])
        target_view = (target[0], target[1], target[2], target[4], target[5])
        embed = self.battle_embed("👑 Batalla especial — recuperar canción", challenger_view, target_view, special=True)
        embed.add_field(
            name="Regla especial",
            value="Si gana el retador, la canción objetivo cambia de propietario. Esta batalla tiene un cooldown largo.",
            inline=False,
        )
        view = ReclaimView(self, battle_id, challenger[0], target[0])
        view.add_item(discord.ui.Button(label=challenger[1][:80], style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label=target[1][:80], style=discord.ButtonStyle.secondary))
        view.children[0].callback = lambda i: view.vote(i, challenger[0])
        view.children[1].callback = lambda i: view.vote(i, target[0])
        view.message = await interaction.followup.send(embed=embed, view=view, wait=True)

    def battle_embed(self, title: str, a: tuple, b: tuple, special: bool = False) -> discord.Embed:
        embed = discord.Embed(title=title)
        embed.add_field(name="A", value=f"**{a[1]}**\n{a[2]}\nELO: `{a[4] if len(a) > 4 else a[5]}`\nPropietario: <@{a[3] if len(a) > 3 else a[4]}>", inline=True)
        embed.add_field(name="B", value=f"**{b[1]}**\n{b[2]}\nELO: `{b[4] if len(b) > 4 else b[5]}`\nPropietario: <@{b[3] if len(b) > 3 else b[4]}>", inline=True)
        embed.set_footer(text="Vota con los botones de abajo.")
        return embed

    async def finish_battle(self, battle_id: int, winner_id: int, votes_a: int, votes_b: int, special: bool) -> None:
        conn = db._conn()
        cur = await conn.execute(
            "SELECT guild_id,song_a_id,song_b_id,status FROM music_battles WHERE id=?",
            (battle_id,),
        )
        battle = await cur.fetchone()
        if not battle or battle[3] != "pending":
            return
        guild_id, a_id, b_id, _ = battle
        loser_id = b_id if winner_id == a_id else a_id

        cur = await conn.execute("SELECT elo,owner_id FROM music_songs WHERE id=?", (winner_id,))
        winner = await cur.fetchone()
        cur = await conn.execute("SELECT elo,owner_id FROM music_songs WHERE id=?", (loser_id,))
        loser = await cur.fetchone()
        if not winner or not loser:
            return

        winner_elo = int(winner[0])
        loser_elo = int(loser[0])
        gain = max(1, round(max(loser_elo, 0) * WIN_GAIN_FRACTION))
        loss = max(1, round(max(winner_elo, 0) * LOSS_FRACTION))
        new_winner = winner_elo + gain
        new_loser = max(0, loser_elo - loss)

        async with db._write_lock:
            await conn.execute(
                "UPDATE music_songs SET elo=?, peak_elo=MAX(peak_elo,?) WHERE id=?",
                (new_winner, new_winner, winner_id),
            )
            await conn.execute("UPDATE music_songs SET elo=? WHERE id=?", (new_loser, loser_id))
            await conn.execute(
                "UPDATE music_battles SET status='finished',ended_at=?,winner_song_id=? WHERE id=?",
                (now_iso(), winner_id, battle_id),
            )

            if special and winner_id == a_id:
                # Challenger's song won. The target song (b_id) transfers to
                # the challenger, while the target owner loses the song.
                cur = await conn.execute("SELECT owner_id FROM music_songs WHERE id=?", (b_id,))
                target_owner = await cur.fetchone()
                challenger_owner = winner[1]
                await conn.execute("UPDATE music_songs SET owner_id=? WHERE id=?", (challenger_owner, b_id))
                await conn.execute(
                    "INSERT INTO music_ownership(guild_id,song_id,owner_id,acquired_at,lost_at) "
                    "VALUES(?,?,?,?,NULL)",
                    (guild_id, b_id, challenger_owner, now_iso()),
                )
                if target_owner:
                    await conn.execute(
                        "UPDATE music_ownership SET lost_at=? WHERE guild_id=? AND song_id=? AND owner_id=? AND lost_at IS NULL",
                        (now_iso(), guild_id, b_id, target_owner[0]),
                    )
            await conn.commit()

    async def cog_unload(self) -> None:
        pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
