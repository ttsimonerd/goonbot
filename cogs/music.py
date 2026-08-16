"""GoonBot music collection and battle system.

Commands:
  /music add <url>        Add a song to your collection.
  /music list [@member]   List a member's song collection (defaults to you).
  /music history          Show recent battles.
  /music info <url>       Show song ownership/ELO.
  /music battle           Start a normal battle between two songs.
  /music reclaim <url>    Challenge the current owner of a song.

The database schema lives in ``db.py`` (the single source of truth, created by
``init_db()`` on startup). This cog only reads/writes those tables.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
import re
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

import db

logger = logging.getLogger(__name__)

NORMAL_COOLDOWN = 60
RECLAIM_COOLDOWN = 60 * 60 * 24 * 3
INITIAL_ELO = 1000
WIN_GAIN_FRACTION = 0.50
LOSS_FRACTION = 0.25
EXTRACT_TIMEOUT = 45

_URL_RE = re.compile(r"https?://\S+")

# Platforms we treat as "music links" when scanning chat. yt-dlp resolves the
# final metadata; this list just stops us from treating every URL as music.
MUSIC_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "music.youtube.com",
    "spotify.com",
    "open.spotify.com",
    "play.spotify.com",
    "spotify.link",
    "soundcloud.com",
    "music.apple.com",
    "deezer.com",
    "bandcamp.com",
)

# Columns selected for every music_songs row, in a fixed order that
# ``_song_dict`` maps back into a dict (so no more fragile index arithmetic).
SONG_COLUMNS = (
    "id, guild_id, title, artist, url, normalized_url, platform, "
    "owner_id, is_original, elo, peak_elo, created_at"
)


def _song_dict(row: Any) -> dict[str, Any]:
    """Map a ``SELECT {SONG_COLUMNS}`` row into a named dict."""
    return {
        "id": row[0],
        "guild_id": row[1],
        "title": row[2],
        "artist": row[3],
        "url": row[4],
        "normalized_url": row[5],
        "platform": row[6],
        "owner_id": int(row[7]),
        "is_original": bool(row[8]),
        "elo": int(row[9]),
        "peak_elo": int(row[10]),
        "created_at": row[11],
    }


def _find_music_urls(text: str) -> list[str]:
    """Extract unique music-platform URLs from a message's raw text."""
    urls: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.findall(text):
        url = match.rstrip(")>].,!?;\"")
        if url in seen:
            continue
        host = url.split("//")[-1].split("/")[0].lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        if any(host == d or host.endswith("." + d) for d in MUSIC_DOMAINS):
            seen.add(url)
            urls.append(url)
    return urls


def now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat()


_SPOTIFY_ENTITY_TYPES = ("track", "album", "playlist", "episode", "show", "artist")


def _normalize_spotify(url: str) -> str | None:
    """Canonicalize a Spotify web URL to ``https://open.spotify.com/{type}/{id}``.

    Returns ``None`` when the URL isn't a Spotify web URL, so callers fall
    through to the generic normalization.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if host not in ("open.spotify.com", "spotify.com", "play.spotify.com"):
        return None

    parts = [part for part in parsed.path.split("/") if part]
    for i, part in enumerate(parts):
        if part in _SPOTIFY_ENTITY_TYPES and i + 1 < len(parts):
            return f"https://open.spotify.com/{part}/{parts[i + 1]}"
    return None


def normalize_url(url: str) -> str:
    url = url.strip()

    # Spotify URLs carry tracking params (?si=, ?context=, ?utm_*) that change
    # per share — strip them so the same track isn't treated as a duplicate.
    spotify = _normalize_spotify(url)
    if spotify:
        return spotify

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
    """Resolve a music URL to (title, artist, canonical_url) via yt-dlp."""
    loop = asyncio.get_running_loop()

    def _extract() -> tuple[str, str, str]:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("track") or info.get("title") or "Unknown title"
            # Spotify returns multiple artists as a list, unlike YouTube's
            # single uploader/channel string.
            artist = info.get("artist") or info.get("uploader") or info.get("channel")
            if isinstance(artist, (list, tuple)):
                artist = ", ".join(str(a) for a in artist if a)
            artist = artist or "Unknown artist"
            webpage = info.get("webpage_url") or url
            return title, artist, webpage

    try:
        return await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=EXTRACT_TIMEOUT)
    except asyncio.TimeoutError as exc:
        raise RuntimeError("Se agotó el tiempo obteniendo la canción. Inténtalo de nuevo.") from exc


class MusicBattleView(discord.ui.View):
    """Botones para votar en una batalla musical normal."""

    def __init__(self, cog: "Music", battle_id: int, song_a: int, song_b: int) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.battle_id = battle_id
        self.song_a = song_a
        self.song_b = song_b
        self.votes: dict[int, int] = {}
        self.message: discord.Message | None = None

    async def _tally(self) -> tuple[int, int]:
        a = sum(v == self.song_a for v in self.votes.values())
        b = sum(v == self.song_b for v in self.votes.values())
        return a, b

    async def _disable_and_edit(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def vote(self, interaction: discord.Interaction, song_id: int) -> None:
        if interaction.user.bot:
            return
        self.votes[interaction.user.id] = song_id
        await self.cog.record_vote(interaction.guild_id, self.battle_id, interaction.user.id, song_id)
        await interaction.response.send_message("Voto registrado.", ephemeral=True)

        a, b = await self._tally()
        if a + b >= 3:
            await self.finish(interaction.channel, a, b)

    async def finish(self, channel: discord.abc.Messageable | None, a: int, b: int) -> None:
        if self.message is None:
            return
        winner = self.song_a if a > b else self.song_b if b > a else random.choice([self.song_a, self.song_b])
        await self.cog.finish_battle(self.battle_id, winner, a, b, special=False)
        await self._disable_and_edit()
        if channel:
            await channel.send(f"**Batalla terminada:** ganó la canción con ID `{winner}`.")

    async def on_timeout(self) -> None:
        """Resolve (or cancel) the battle when nobody reaches the vote threshold."""
        a, b = await self._tally()
        if a + b == 0:
            await self.cog.cancel_battle(self.battle_id)
        else:
            winner = self.song_a if a > b else self.song_b if b > a else random.choice([self.song_a, self.song_b])
            await self.cog.finish_battle(self.battle_id, winner, a, b, special=False)
        await self._disable_and_edit()
        if self.message is not None and self.message.channel is not None:
            msg = "**Batalla cancelada:** nadie votó a tiempo." if a + b == 0 else "**Batalla terminada por tiempo.**"
            try:
                await self.message.channel.send(msg)
            except discord.HTTPException:
                pass


class ReclaimView(discord.ui.View):
    """Botones para votar en una batalla especial de recuperación."""

    def __init__(self, cog: "Music", battle_id: int, challenger_song: int, target_song: int) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.battle_id = battle_id
        self.challenger_song = challenger_song
        self.target_song = target_song
        self.votes: dict[int, int] = {}
        self.message: discord.Message | None = None

    async def _tally(self) -> tuple[int, int]:
        a = sum(v == self.challenger_song for v in self.votes.values())
        b = sum(v == self.target_song for v in self.votes.values())
        return a, b

    async def _disable_and_edit(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def vote(self, interaction: discord.Interaction, song_id: int) -> None:
        if interaction.user.bot:
            return
        self.votes[interaction.user.id] = song_id
        await self.cog.record_vote(interaction.guild_id, self.battle_id, interaction.user.id, song_id)
        await interaction.response.send_message("Voto registrado.", ephemeral=True)

        a, b = await self._tally()
        if a + b >= 5:
            await self.finish(interaction.channel, a, b)

    async def finish(self, channel: discord.abc.Messageable | None, a: int, b: int) -> None:
        if self.message is None:
            return
        winner = self.challenger_song if a > b else self.target_song if b > a else random.choice([self.challenger_song, self.target_song])
        await self.cog.finish_battle(self.battle_id, winner, a, b, special=True)
        await self._disable_and_edit()
        if channel:
            await channel.send(
                "**Batalla especial terminada.** La canción se queda con su propietario actual salvo que el retador haya ganado."
            )

    async def on_timeout(self) -> None:
        """Resolve (or cancel) the reclaim battle on timeout."""
        a, b = await self._tally()
        if a + b == 0:
            await self.cog.cancel_battle(self.battle_id)
        else:
            winner = self.challenger_song if a > b else self.target_song if b > a else random.choice([self.challenger_song, self.target_song])
            await self.cog.finish_battle(self.battle_id, winner, a, b, special=True)
        await self._disable_and_edit()
        if self.message is not None and self.message.channel is not None:
            msg = "**Batalla especial cancelada:** nadie votó a tiempo." if a + b == 0 else "**Batalla especial terminada por tiempo.**"
            try:
                await self.message.channel.send(msg)
            except discord.HTTPException:
                pass


class Music(commands.GroupCog, group_name="music", description="Colección de canciones y batallas"):
    """Colección de canciones, propiedad y sistema de batallas musicales."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Auto-adds music links shared in the configured music channel."""
        if message.author.bot or message.guild is None:
            return
        # Cheap early exit: only hit the DB when the message actually has a URL.
        if not _URL_RE.search(message.content):
            return

        settings = await db.get_settings(message.guild.id)
        music_channel_id = settings.get("music_channel_id")
        if music_channel_id is None or message.channel.id != music_channel_id:
            return

        for url in _find_music_urls(message.content):
            result = await self._add_song_to_user(message.guild.id, message.author.id, url)

            if result["status"] == "added":
                embed = discord.Embed(
                    title="🎵 Canción añadida",
                    description=f"**{result['title']}**\n{result['artist']}",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Propietario", value=message.author.mention)
                embed.set_footer(text="Añadida desde un enlace compartido")
                await message.channel.send(embed=embed)
            elif result["status"] == "duplicate":
                await message.channel.send(
                    f"⚠️ {message.author.mention}, esa canción ya está adjudicada a <@{result['owner_id']}>.",
                    delete_after=15,
                )
            else:
                logger.warning("Couldn't auto-add music link %s: %s", url, result.get("error"))

    # ------------------------------------------------------------------
    # Song lookup helpers (dict-based)
    # ------------------------------------------------------------------

    async def song_by_id(self, guild_id: int, song_id: int) -> dict[str, Any] | None:
        cur = await db._conn().execute(
            f"SELECT {SONG_COLUMNS} FROM music_songs "
            "WHERE guild_id=? AND id=? AND deleted_at IS NULL",
            (str(guild_id), song_id),
        )
        row = await cur.fetchone()
        return _song_dict(row) if row else None

    async def song_by_url(self, guild_id: int, url: str) -> dict[str, Any] | None:
        cur = await db._conn().execute(
            f"SELECT {SONG_COLUMNS} FROM music_songs "
            "WHERE guild_id=? AND normalized_url=? AND deleted_at IS NULL",
            (str(guild_id), normalize_url(url)),
        )
        row = await cur.fetchone()
        return _song_dict(row) if row else None

    async def owner_song(self, guild_id: int, owner_id: int) -> dict[str, Any] | None:
        """Highest-ELO song owned by a user (used as their reclaim champion)."""
        cur = await db._conn().execute(
            f"SELECT {SONG_COLUMNS} FROM music_songs "
            "WHERE guild_id=? AND owner_id=? AND deleted_at IS NULL "
            "ORDER BY elo DESC, id ASC LIMIT 1",
            (str(guild_id), str(owner_id)),
        )
        row = await cur.fetchone()
        return _song_dict(row) if row else None

    async def songs_by_owner(self, guild_id: int, owner_id: int) -> list[dict[str, Any]]:
        """All songs owned by a user, best ELO first."""
        cur = await db._conn().execute(
            f"SELECT {SONG_COLUMNS} FROM music_songs "
            "WHERE guild_id=? AND owner_id=? AND deleted_at IS NULL "
            "ORDER BY elo DESC, id ASC",
            (str(guild_id), str(owner_id)),
        )
        rows = await cur.fetchall()
        return [_song_dict(r) for r in rows]

    async def random_songs(self, guild_id: int, limit: int = 2) -> list[dict[str, Any]]:
        """Random songs that aren't already locked in a pending battle."""
        cur = await db._conn().execute(
            f"SELECT {SONG_COLUMNS} FROM music_songs "
            "WHERE guild_id=? AND deleted_at IS NULL "
            "AND id NOT IN (SELECT song_a_id FROM music_battles WHERE status='pending') "
            "AND id NOT IN (SELECT song_b_id FROM music_battles WHERE status='pending') "
            "ORDER BY RANDOM() LIMIT ?",
            (str(guild_id), limit),
        )
        rows = await cur.fetchall()
        return [_song_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Cooldowns
    # ------------------------------------------------------------------

    async def cooldown_remaining(self, guild_id: int, user_id: int, kind: str) -> int:
        cur = await db._conn().execute(
            "SELECT available_at FROM music_cooldowns WHERE guild_id=? AND user_id=? AND cooldown_type=?",
            (str(guild_id), str(user_id), kind),
        )
        row = await cur.fetchone()
        if not row:
            return 0
        try:
            available = dt.datetime.fromisoformat(row[0])
            left = int((available - dt.datetime.utcnow()).total_seconds())
            return max(0, left)
        except (ValueError, TypeError):
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

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    async def _add_song_to_user(self, guild_id: int, user_id: int, url: str) -> dict[str, Any]:
        """Adds a song to a user's collection if it isn't already claimed.

        Returns a dict describing the outcome:
          {"status": "duplicate", "owner_id": int, "title": str}
          {"status": "error", "error": str}
          {"status": "added", "title": str, "artist": str, "url": str}
        """
        existing = await self.song_by_url(guild_id, url)
        if existing:
            return {"status": "duplicate", "owner_id": existing["owner_id"], "title": existing["title"]}

        try:
            title, artist, final_url = await extract_song(url)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        norm = normalize_url(final_url)
        existing = await self.song_by_url(guild_id, norm)
        if existing:
            return {"status": "duplicate", "owner_id": existing["owner_id"], "title": existing["title"]}

        platform = (
            "spotify"
            if "spotify" in final_url
            else "youtube"
            if "youtube.com" in final_url or "youtu.be" in final_url
            else "other"
        )

        async with db._write_lock:
            cur = await db._conn().execute(
                "INSERT INTO music_songs(guild_id,title,artist,url,normalized_url,platform,owner_id,is_original,elo,peak_elo,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (str(guild_id), title, artist, final_url, norm, platform,
                 str(user_id), 0, INITIAL_ELO, INITIAL_ELO, now_iso()),
            )
            song_id = cur.lastrowid
            await db._conn().execute(
                "INSERT INTO music_ownership(guild_id,song_id,owner_id,acquired_at) VALUES(?,?,?,?)",
                (str(guild_id), song_id, str(user_id), now_iso()),
            )
            await db._conn().commit()

        return {"status": "added", "title": title, "artist": artist, "url": final_url}

    async def record_vote(self, guild_id: int, battle_id: int, user_id: int, song_id: int) -> None:
        """Persist a vote, allowing a user to change their vote."""
        async with db._write_lock:
            await db._conn().execute(
                "INSERT INTO music_votes(guild_id,battle_id,user_id,song_id,voted_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(battle_id,user_id) DO UPDATE SET song_id=excluded.song_id, voted_at=excluded.voted_at",
                (str(guild_id), battle_id, str(user_id), song_id, now_iso()),
            )
            await db._conn().commit()

    async def cancel_battle(self, battle_id: int) -> None:
        """Mark a pending battle as cancelled (e.g. it timed out with no votes)."""
        async with db._write_lock:
            await db._conn().execute(
                "UPDATE music_battles SET status='cancelled', ended_at=? WHERE id=? AND status='pending'",
                (now_iso(), battle_id),
            )
            await db._conn().commit()

    async def finish_battle(self, battle_id: int, winner_id: int, votes_a: int, votes_b: int, special: bool) -> None:
        """Apply a battle's outcome atomically: ELO, history, and (for reclaims) ownership."""
        conn = db._conn()
        async with db._write_lock:
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

            await conn.execute(
                "UPDATE music_songs SET elo=?, peak_elo=MAX(peak_elo,?) WHERE id=?",
                (new_winner, new_winner, winner_id),
            )
            await conn.execute("UPDATE music_songs SET elo=? WHERE id=?", (new_loser, loser_id))
            await conn.execute(
                "UPDATE music_battles SET status='finished',ended_at=?,winner_song_id=? WHERE id=?",
                (now_iso(), winner_id, battle_id),
            )

            # ELO history for both songs.
            await conn.execute(
                "INSERT INTO music_elo_history(guild_id,song_id,old_elo,new_elo,change,reason,reference_id,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (guild_id, winner_id, winner_elo, new_winner, gain, "battle", battle_id, now_iso()),
            )
            await conn.execute(
                "INSERT INTO music_elo_history(guild_id,song_id,old_elo,new_elo,change,reason,reference_id,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (guild_id, loser_id, loser_elo, new_loser, -loss, "battle", battle_id, now_iso()),
            )

            if special and winner_id == a_id:
                # Challenger won: the target song (b_id) transfers to them.
                challenger_owner = winner[1]
                cur = await conn.execute("SELECT owner_id FROM music_songs WHERE id=?", (b_id,))
                target_row = await cur.fetchone()
                await conn.execute("UPDATE music_songs SET owner_id=? WHERE id=?", (challenger_owner, b_id))
                await conn.execute(
                    "INSERT INTO music_ownership(guild_id,song_id,owner_id,acquired_at,acquisition_type,claim_battle_id) "
                    "VALUES(?,?,?,?,?,?)",
                    (guild_id, b_id, challenger_owner, now_iso(), "claim", battle_id),
                )
                if target_row:
                    await conn.execute(
                        "UPDATE music_ownership SET lost_at=? WHERE guild_id=? AND song_id=? AND owner_id=? AND lost_at IS NULL",
                        (now_iso(), guild_id, b_id, target_row[0]),
                    )

            await conn.commit()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @app_commands.command(name="add", description="Añade una canción y te la adjudica.")
    @app_commands.describe(url="URL de YouTube u otra plataforma compatible")
    async def add(self, interaction: discord.Interaction, url: str) -> None:
        """Añade una canción y te la adjudica."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Este comando solo funciona dentro de un servidor.", ephemeral=True)
            return
        result = await self._add_song_to_user(interaction.guild_id, interaction.user.id, url)

        if result["status"] == "duplicate":
            await interaction.followup.send(
                f"**Duplicada.** Esta canción ya está adjudicada a <@{result['owner_id']}>.\n"
                "Puedes usar `/music reclaim` para intentar recuperarla mediante una batalla especial.",
                ephemeral=True,
            )
            return

        if result["status"] == "error":
            await interaction.followup.send(f"No he podido obtener la canción: `{result['error']}`", ephemeral=True)
            return

        embed = discord.Embed(
            title="Canción adjudicada",
            description=f"**{result['title']}**\n{result['artist']}",
        )
        embed.add_field(name="Propietario", value=interaction.user.mention)
        embed.add_field(name="ELO", value=str(INITIAL_ELO))
        embed.add_field(name="Información", value="Esta canción queda asociada a ti hasta que pierdas una batalla especial.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="list", description="Muestra tu colección de canciones (o la de otro miembro).")
    @app_commands.describe(member="Miembro cuya colección quieres ver (opcional)")
    async def list_songs(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        """Muestra la colección de canciones de un miembro, ordenada por ELO."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Solo disponible en servidores.", ephemeral=True)
            return

        target = member or interaction.user
        songs = await self.songs_by_owner(interaction.guild_id, target.id)
        if not songs:
            await interaction.followup.send(
                f"**{target.display_name}** no tiene canciones adjudicadas todavía.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"🎵 Colección de {target.display_name}",
            color=discord.Color.blurple(),
        )
        lines = [f"`#{s['id']}` **{s['title']}** — {s['artist']} · ELO `{s['elo']}`" for s in songs]
        embed.description = "\n".join(lines[:25])
        embed.set_footer(text=f"{len(songs)} canciones" + (" · mostrando las 25 mejores" if len(songs) > 25 else ""))
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
        embed = discord.Embed(title=song["title"], description=song["artist"], url=song["url"])
        embed.add_field(name="Propietario", value=f"<@{song['owner_id']}>")
        embed.add_field(name="ELO", value=str(song["elo"]))
        embed.add_field(name="ELO máximo", value=str(song["peak_elo"]))
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

        songs = await self.random_songs(interaction.guild_id, 2)
        if len(songs) < 2:
            await interaction.followup.send("Necesito al menos dos canciones adjudicadas.")
            return

        a, b = songs
        async with db._write_lock:
            cur = await db._conn().execute(
                "INSERT INTO music_battles(guild_id,song_a_id,song_b_id,battle_type,started_at,channel_id,status) "
                "VALUES(?,?,?,?,?,?,?)",
                (str(interaction.guild_id), a["id"], b["id"], "normal", now_iso(), str(interaction.channel_id), "pending"),
            )
            battle_id = cur.lastrowid
            await db._conn().commit()
        await self.set_cooldown(interaction.guild_id, interaction.user.id, "normal", NORMAL_COOLDOWN)

        embed = self.battle_embed("⚔️ Batalla musical", a, b)
        view = MusicBattleView(self, battle_id, a["id"], b["id"])
        view.add_item(discord.ui.Button(label=a["title"][:80], style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label=b["title"][:80], style=discord.ButtonStyle.secondary))
        view.children[0].callback = lambda i: view.vote(i, a["id"])
        view.children[1].callback = lambda i: view.vote(i, b["id"])
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
        if target["owner_id"] == interaction.user.id:
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
                (str(interaction.guild_id), challenger["id"], target["id"], "reclaim", now_iso(), str(interaction.channel_id), "pending"),
            )
            battle_id = cur.lastrowid
            await db._conn().commit()
        await self.set_cooldown(interaction.guild_id, interaction.user.id, "reclaim", RECLAIM_COOLDOWN)

        embed = self.battle_embed("👑 Batalla especial — recuperar canción", challenger, target)
        embed.add_field(
            name="Regla especial",
            value="Si gana el retador, la canción objetivo cambia de propietario. Esta batalla tiene un cooldown largo.",
            inline=False,
        )
        view = ReclaimView(self, battle_id, challenger["id"], target["id"])
        view.add_item(discord.ui.Button(label=challenger["title"][:80], style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label=target["title"][:80], style=discord.ButtonStyle.secondary))
        view.children[0].callback = lambda i: view.vote(i, challenger["id"])
        view.children[1].callback = lambda i: view.vote(i, target["id"])
        view.message = await interaction.followup.send(embed=embed, view=view, wait=True)

    def battle_embed(self, title: str, a: dict[str, Any], b: dict[str, Any]) -> discord.Embed:
        """Build the battle embed from two song dicts."""
        embed = discord.Embed(title=title)
        embed.add_field(
            name="A",
            value=f"**{a['title']}**\n{a['artist']}\nELO: `{a['elo']}`\nPropietario: <@{a['owner_id']}>",
            inline=True,
        )
        embed.add_field(
            name="B",
            value=f"**{b['title']}**\n{b['artist']}\nELO: `{b['elo']}`\nPropietario: <@{b['owner_id']}>",
            inline=True,
        )
        embed.set_footer(text="Vota con los botones de abajo.")
        return embed


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
