"""
Async SQLite layer for GoonBot's economy, gambling settings, votebet
predictions, dashboard, and music system.

One shared connection (WAL mode, so reads don't block on writes) plus an
asyncio.Lock around writes, since SQLite only wants one writer at a time
and this all runs in the same event loop as the Discord gateway connection.

Set GOONBOT_DB_PATH to a path inside a mounted volume so data survives
redeploys — see Dockerfile/README for the Coolify volume setup.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
from typing import Any, Optional

import aiosqlite

DB_PATH = os.getenv("GOONBOT_DB_PATH", "data/goonbot.db")

_connection: Optional[aiosqlite.Connection] = None
_write_lock = asyncio.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS economy (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    money INTEGER NOT NULL DEFAULT 100,
    warns INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    daily_claimed TEXT,
    daily_streak INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS predictions (
    guild_id TEXT NOT NULL,
    bet_id TEXT NOT NULL,
    creator_id TEXT NOT NULL,
    description TEXT NOT NULL,
    amount INTEGER NOT NULL,
    days INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    resolve_at TEXT NOT NULL,
    multiplier REAL NOT NULL,
    success_chance REAL NOT NULL,
    settled INTEGER NOT NULL DEFAULT 0,
    result TEXT,
    channel_id TEXT,
    message_id TEXT,
    PRIMARY KEY (guild_id, bet_id)
);

CREATE TABLE IF NOT EXISTS settings (
    guild_id TEXT PRIMARY KEY,
    gambling_channel_id TEXT,
    gambling_lockout_hours INTEGER NOT NULL DEFAULT 24,
    gambling_max_warns INTEGER NOT NULL DEFAULT 3,
    gambling_winners_channel_id TEXT,
    suggestions_channel_id TEXT,
    music_channel_id TEXT
);

CREATE TABLE IF NOT EXISTS dashboard_users (
    discord_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    avatar_url TEXT,
    messages_used_today INTEGER NOT NULL DEFAULT 0,
    last_reset_date TEXT
);

CREATE TABLE IF NOT EXISTS message_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id TEXT NOT NULL,
    channel_key TEXT NOT NULL,
    content TEXT NOT NULL,
    sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS allowed_channels (
    channel_key TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    label TEXT NOT NULL,
    allowed_roles TEXT NOT NULL DEFAULT '[]',
    allowed_users TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS dashboard_config (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS saved_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- -------------------------------------------------------------------------
-- Music system
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS music_songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    platform TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    is_original INTEGER NOT NULL DEFAULT 0,
    elo INTEGER NOT NULL DEFAULT 0,
    peak_elo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_music_songs_guild_url
ON music_songs (guild_id, normalized_url);

CREATE INDEX IF NOT EXISTS idx_music_songs_guild
ON music_songs (guild_id);

CREATE INDEX IF NOT EXISTS idx_music_songs_owner
ON music_songs (guild_id, owner_id);

CREATE INDEX IF NOT EXISTS idx_music_songs_elo
ON music_songs (guild_id, elo DESC);

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
    message_id TEXT,
    FOREIGN KEY (song_a_id) REFERENCES music_songs(id),
    FOREIGN KEY (song_b_id) REFERENCES music_songs(id),
    FOREIGN KEY (winner_song_id) REFERENCES music_songs(id)
);

CREATE INDEX IF NOT EXISTS idx_music_battles_guild
ON music_battles (guild_id);

CREATE INDEX IF NOT EXISTS idx_music_battles_song_a
ON music_battles (song_a_id);

CREATE INDEX IF NOT EXISTS idx_music_battles_song_b
ON music_battles (song_b_id);

CREATE INDEX IF NOT EXISTS idx_music_battles_status
ON music_battles (guild_id, status);

CREATE TABLE IF NOT EXISTS music_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    battle_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    song_id INTEGER NOT NULL,
    voted_at TEXT NOT NULL,
    FOREIGN KEY (battle_id) REFERENCES music_battles(id),
    FOREIGN KEY (song_id) REFERENCES music_songs(id),
    UNIQUE (battle_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_music_votes_battle
ON music_votes (battle_id);

CREATE INDEX IF NOT EXISTS idx_music_votes_user
ON music_votes (guild_id, user_id);

CREATE TABLE IF NOT EXISTS music_ownership (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    song_id INTEGER NOT NULL,
    owner_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    lost_at TEXT,
    acquisition_type TEXT NOT NULL DEFAULT 'original',
    claim_battle_id INTEGER,
    FOREIGN KEY (song_id) REFERENCES music_songs(id),
    FOREIGN KEY (claim_battle_id) REFERENCES music_battles(id)
);

CREATE INDEX IF NOT EXISTS idx_music_ownership_song
ON music_ownership (guild_id, song_id);

CREATE INDEX IF NOT EXISTS idx_music_ownership_owner
ON music_ownership (guild_id, owner_id);

CREATE TABLE IF NOT EXISTS music_sotd (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    song_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    positive_votes INTEGER NOT NULL DEFAULT 0,
    negative_votes INTEGER NOT NULL DEFAULT 0,
    elo_change INTEGER NOT NULL DEFAULT 0,
    boost INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (song_id) REFERENCES music_songs(id)
);

CREATE INDEX IF NOT EXISTS idx_music_sotd_guild
ON music_sotd (guild_id);

CREATE INDEX IF NOT EXISTS idx_music_sotd_song
ON music_sotd (guild_id, song_id);

CREATE TABLE IF NOT EXISTS music_elo_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    song_id INTEGER NOT NULL,
    old_elo INTEGER NOT NULL,
    new_elo INTEGER NOT NULL,
    change INTEGER NOT NULL,
    reason TEXT NOT NULL,
    reference_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (song_id) REFERENCES music_songs(id)
);

CREATE INDEX IF NOT EXISTS idx_music_elo_history_song
ON music_elo_history (guild_id, song_id);

CREATE INDEX IF NOT EXISTS idx_music_elo_history_created
ON music_elo_history (guild_id, created_at DESC);

CREATE TABLE IF NOT EXISTS music_cooldowns (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    cooldown_type TEXT NOT NULL,
    available_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, cooldown_type)
);
"""


async def init_db() -> None:
    """Call once on bot startup before any cog touches the DB."""
    global _connection

    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)

    _connection = await aiosqlite.connect(DB_PATH)

    await _connection.execute("PRAGMA journal_mode=WAL;")
    await _connection.execute("PRAGMA foreign_keys=ON;")

    await _connection.executescript(SCHEMA)
    await _migrate()
    await _connection.commit()


async def _migrate() -> None:
    """Apply lightweight migrations for columns added after the initial schema."""
    cursor = await _connection.execute("PRAGMA table_info(settings)")
    rows = await cursor.fetchall()
    columns = {row[1] for row in rows}

    if "music_channel_id" not in columns:
        await _connection.execute(
            "ALTER TABLE settings ADD COLUMN music_channel_id TEXT"
        )

    cursor = await _connection.execute("PRAGMA table_info(economy)")
    rows = await cursor.fetchall()
    columns = {row[1] for row in rows}

    if "daily_streak" not in columns:
        await _connection.execute(
            "ALTER TABLE economy ADD COLUMN daily_streak INTEGER NOT NULL DEFAULT 0"
        )

    cursor = await _connection.execute("PRAGMA table_info(allowed_channels)")
    rows = await cursor.fetchall()
    columns = {row[1] for row in rows}

    if "allowed_roles" not in columns:
        await _connection.execute(
            "ALTER TABLE allowed_channels "
            "ADD COLUMN allowed_roles TEXT NOT NULL DEFAULT '[]'"
        )
    if "allowed_users" not in columns:
        await _connection.execute(
            "ALTER TABLE allowed_channels "
            "ADD COLUMN allowed_users TEXT NOT NULL DEFAULT '[]'"
        )

    # Backfill music_songs.platform for rows added before per-platform tagging
    # existed (they defaulted to 'other'). Infer from the stored URL; rows we
    # can't classify stay 'other', so this stays a cheap no-op after one run.
    cursor = await _connection.execute(
        "SELECT id, normalized_url FROM music_songs "
        "WHERE platform = 'other' OR platform = ''"
    )
    backfill_rows = await cursor.fetchall()
    for song_id, song_url in backfill_rows:
        inferred = infer_platform(song_url)
        if inferred != "other":
            await _connection.execute(
                "UPDATE music_songs SET platform = ? WHERE id = ?",
                (inferred, song_id),
            )


async def close_db() -> None:
    """Call on bot shutdown so aiosqlite's background thread exits cleanly."""
    global _connection

    if _connection is not None:
        await _connection.close()
        _connection = None


def _conn() -> aiosqlite.Connection:
    if _connection is None:
        raise RuntimeError(
            "Database not initialized — call init_db() on startup."
        )

    return _connection


def infer_platform(url: str) -> str:
    """Classify a song's source platform from its URL.

    Shared by the runtime insert path and the startup backfill migration, so
    both stay in sync on the set of recognised platforms.
    """
    u = (url or "").lower()
    if "spotify" in u:
        return "spotify"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "soundcloud.com" in u:
        return "soundcloud"
    if "music.apple.com" in u or "itunes.apple.com" in u:
        return "apple_music"
    if "deezer.com" in u:
        return "deezer"
    if "bandcamp.com" in u:
        return "bandcamp"
    return "other"


# ---------------------------------------------------------------------------
# Economy (money / warns / lockout / daily claim)
# ---------------------------------------------------------------------------

DEFAULT_USER = {
    "money": 100,
    "warns": 0,
    "locked_until": None,
    "daily_claimed": None,
    "daily_streak": 0,
}


async def get_user(guild_id: int, user_id: int) -> dict[str, Any]:
    db = _conn()

    cursor = await db.execute(
        "SELECT money, warns, locked_until, daily_claimed, daily_streak "
        "FROM economy WHERE guild_id = ? AND user_id = ?",
        (str(guild_id), str(user_id)),
    )

    row = await cursor.fetchone()

    if row is None:
        async with _write_lock:
            await db.execute(
                "INSERT OR IGNORE INTO economy "
                "(guild_id, user_id, money, warns, locked_until, daily_claimed) "
                "VALUES (?, ?, 100, 0, NULL, NULL)",
                (str(guild_id), str(user_id)),
            )
            await db.commit()

        return dict(DEFAULT_USER)

    return {
        "money": row[0],
        "warns": row[1],
        "locked_until": row[2],
        "daily_claimed": row[3],
        "daily_streak": row[4],
    }


async def update_user(
    guild_id: int,
    user_id: int,
    **fields: Any,
) -> None:
    """Partial update, e.g. update_user(gid, uid, money=150, warns=0)."""
    if not fields:
        return

    await get_user(guild_id, user_id)

    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [str(guild_id), str(user_id)]

    db = _conn()

    async with _write_lock:
        await db.execute(
            f"UPDATE economy SET {columns} "
            "WHERE guild_id = ? AND user_id = ?",
            values,
        )
        await db.commit()


async def add_money(
    guild_id: int,
    user_id: int,
    amount: int,
) -> int:
    """
    Adds (or subtracts, if negative) coins, floored at 0.
    Returns new balance.

    Does the read-modify-write as a single locked SQL UPDATE so concurrent
    calls for the same user cannot race and silently drop updates.
    """
    db_conn = _conn()

    async with _write_lock:
        await db_conn.execute(
            "INSERT OR IGNORE INTO economy "
            "(guild_id, user_id, money, warns, locked_until, daily_claimed) "
            "VALUES (?, ?, 100, 0, NULL, NULL)",
            (str(guild_id), str(user_id)),
        )

        await db_conn.execute(
            "UPDATE economy "
            "SET money = MAX(0, money + ?) "
            "WHERE guild_id = ? AND user_id = ?",
            (amount, str(guild_id), str(user_id)),
        )

        cursor = await db_conn.execute(
            "SELECT money FROM economy "
            "WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        )

        row = await cursor.fetchone()

        await db_conn.commit()

        return row[0]


async def get_top_balances(
    guild_id: int,
    limit: int = 5,
) -> list[tuple[str, int]]:
    db = _conn()

    cursor = await db.execute(
        "SELECT user_id, money FROM economy "
        "WHERE guild_id = ? "
        "ORDER BY money DESC LIMIT ?",
        (str(guild_id), limit),
    )

    rows = await cursor.fetchall()

    return [(row[0], row[1]) for row in rows]


async def get_locked_users(guild_id: int) -> list[tuple[str, str]]:
    """Return (user_id, locked_until) for every user currently locked out."""
    db = _conn()

    cursor = await db.execute(
        "SELECT user_id, locked_until FROM economy "
        "WHERE guild_id = ? AND locked_until IS NOT NULL",
        (str(guild_id),),
    )

    rows = await cursor.fetchall()

    return [(row[0], row[1]) for row in rows]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "gambling_channel_id": None,
    "gambling_lockout_hours": 24,
    "gambling_max_warns": 3,
    "gambling_winners_channel_id": None,
    "suggestions_channel_id": None,
    "music_channel_id": None,
}


async def get_settings(guild_id: int) -> dict[str, Any]:
    db = _conn()

    cursor = await db.execute(
        "SELECT gambling_channel_id, gambling_lockout_hours, "
        "gambling_max_warns, gambling_winners_channel_id, "
        "suggestions_channel_id, music_channel_id "
        "FROM settings WHERE guild_id = ?",
        (str(guild_id),),
    )

    row = await cursor.fetchone()

    if row is None:
        async with _write_lock:
            await db.execute(
                "INSERT OR IGNORE INTO settings (guild_id) VALUES (?)",
                (str(guild_id),),
            )
            await db.commit()

        return dict(DEFAULT_SETTINGS)

    return {
        "gambling_channel_id": int(row[0]) if row[0] else None,
        "gambling_lockout_hours": row[1],
        "gambling_max_warns": row[2],
        "gambling_winners_channel_id": int(row[3]) if row[3] else None,
        "suggestions_channel_id": int(row[4]) if row[4] else None,
        "music_channel_id": int(row[5]) if row[5] else None,
    }


async def update_settings(
    guild_id: int,
    **fields: Any,
) -> None:
    if not fields:
        return

    await get_settings(guild_id)

    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [str(guild_id)]

    db = _conn()

    async with _write_lock:
        await db.execute(
            f"UPDATE settings SET {columns} WHERE guild_id = ?",
            values,
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Predictions (votebet)
# ---------------------------------------------------------------------------

async def create_prediction(
    guild_id: int,
    bet_id: str,
    **fields: Any,
) -> None:
    db = _conn()

    columns = ["guild_id", "bet_id"] + list(fields.keys())
    placeholders = ", ".join("?" for _ in columns)
    values = [str(guild_id), bet_id] + list(fields.values())

    async with _write_lock:
        await db.execute(
            f"INSERT INTO predictions ({', '.join(columns)}) "
            f"VALUES ({placeholders})",
            values,
        )
        await db.commit()


async def update_prediction(
    guild_id: int,
    bet_id: str,
    **fields: Any,
) -> None:
    if not fields:
        return

    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [str(guild_id), bet_id]

    db = _conn()

    async with _write_lock:
        await db.execute(
            f"UPDATE predictions SET {columns} "
            "WHERE guild_id = ? AND bet_id = ?",
            values,
        )
        await db.commit()


async def get_predictions(
    guild_id: int,
    include_settled: bool = True,
) -> list[dict[str, Any]]:
    db = _conn()

    query = (
        "SELECT bet_id, creator_id, description, amount, days, "
        "created_at, resolve_at, multiplier, success_chance, settled, "
        "result, channel_id, message_id "
        "FROM predictions WHERE guild_id = ?"
    )

    params: list[Any] = [str(guild_id)]

    if not include_settled:
        query += " AND settled = 0"

    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()

    return [
        {
            "bet_id": r[0],
            "creator_id": r[1],
            "description": r[2],
            "amount": r[3],
            "days": r[4],
            "created_at": r[5],
            "resolve_at": r[6],
            "multiplier": r[7],
            "success_chance": r[8],
            "settled": bool(r[9]),
            "result": r[10],
            "channel_id": int(r[11]) if r[11] else None,
            "message_id": int(r[12]) if r[12] else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Dashboard users (auth cache + daily message limit)
# ---------------------------------------------------------------------------

DAILY_MESSAGE_LIMIT = 3


async def upsert_dashboard_user(
    discord_id: int,
    username: str,
    avatar_url: str | None,
) -> None:
    db = _conn()

    async with _write_lock:
        await db.execute(
            "INSERT INTO dashboard_users "
            "(discord_id, username, avatar_url, messages_used_today, "
            "last_reset_date) "
            "VALUES (?, ?, ?, 0, NULL) "
            "ON CONFLICT(discord_id) DO UPDATE SET "
            "username = excluded.username, "
            "avatar_url = excluded.avatar_url",
            (str(discord_id), username, avatar_url),
        )
        await db.commit()


async def get_dashboard_user(
    discord_id: int,
) -> dict[str, Any] | None:
    """
    Returns the user with the daily counter already reset if a new day has
    started — callers never need to think about the reset separately.
    """
    db = _conn()

    cursor = await db.execute(
        "SELECT discord_id, username, avatar_url, "
        "messages_used_today, last_reset_date "
        "FROM dashboard_users WHERE discord_id = ?",
        (str(discord_id),),
    )

    row = await cursor.fetchone()

    if row is None:
        return None

    today = datetime.date.today().isoformat()
    messages_used_today = row[3]

    if row[4] != today:
        async with _write_lock:
            await db.execute(
                "UPDATE dashboard_users "
                "SET messages_used_today = 0, last_reset_date = ? "
                "WHERE discord_id = ?",
                (today, str(discord_id)),
            )
            await db.commit()

        messages_used_today = 0

    return {
        "discord_id": row[0],
        "username": row[1],
        "avatar_url": row[2],
        "messages_used_today": messages_used_today,
        "messages_remaining": max(
            0,
            DAILY_MESSAGE_LIMIT - messages_used_today,
        ),
    }


async def increment_messages_used(discord_id: int) -> None:
    db = _conn()

    async with _write_lock:
        await db.execute(
            "UPDATE dashboard_users "
            "SET messages_used_today = messages_used_today + 1 "
            "WHERE discord_id = ?",
            (str(discord_id),),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Message logs
# ---------------------------------------------------------------------------

async def log_message(
    discord_id: int,
    channel_key: str,
    content: str,
) -> None:
    db = _conn()

    async with _write_lock:
        await db.execute(
            "INSERT INTO message_logs "
            "(discord_id, channel_key, content, sent_at) "
            "VALUES (?, ?, ?, ?)",
            (
                str(discord_id),
                channel_key,
                content,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()


async def get_recent_messages(
    discord_id: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    db = _conn()

    cursor = await db.execute(
        "SELECT channel_key, content, sent_at "
        "FROM message_logs "
        "WHERE discord_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (str(discord_id), limit),
    )

    rows = await cursor.fetchall()

    return [
        {
            "channel_key": r[0],
            "content": r[1],
            "sent_at": r[2],
        }
        for r in rows
    ]


async def get_all_message_logs(
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """For the admin moderation view — newest first, paginated."""
    db = _conn()

    cursor = await db.execute(
        "SELECT ml.discord_id, du.username, ml.channel_key, "
        "ml.content, ml.sent_at "
        "FROM message_logs ml "
        "LEFT JOIN dashboard_users du "
        "ON ml.discord_id = du.discord_id "
        "ORDER BY ml.id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )

    rows = await cursor.fetchall()

    return [
        {
            "discord_id": r[0],
            "username": r[1] or f"User {r[0]}",
            "channel_key": r[2],
            "content": r[3],
            "sent_at": r[4],
        }
        for r in rows
    ]


async def count_message_logs() -> int:
    """Total number of logged messages (for admin pagination)."""
    db = _conn()

    cursor = await db.execute("SELECT COUNT(*) FROM message_logs")
    row = await cursor.fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Allowed channels
# ---------------------------------------------------------------------------

def _parse_id_list(raw: str | None) -> list[str]:
    """Parse a JSON-encoded list of IDs, tolerating legacy/empty values."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (json.JSONDecodeError, TypeError):
        return []
    return []


def _dump_id_list(ids: list[str] | None) -> str:
    """Serialize a list of IDs to the JSON string stored in the DB."""
    return json.dumps(ids or [])


async def get_allowed_channels() -> list[dict[str, Any]]:
    db = _conn()

    cursor = await db.execute(
        "SELECT channel_key, channel_id, label, allowed_roles, allowed_users "
        "FROM allowed_channels ORDER BY label"
    )

    rows = await cursor.fetchall()

    return [
        {
            "channel_key": r[0],
            "channel_id": int(r[1]),
            "label": r[2],
            "allowed_roles": _parse_id_list(r[3]),
            "allowed_users": _parse_id_list(r[4]),
        }
        for r in rows
    ]


async def get_allowed_channel(
    channel_key: str,
) -> dict[str, Any] | None:
    db = _conn()

    cursor = await db.execute(
        "SELECT channel_key, channel_id, label, allowed_roles, allowed_users "
        "FROM allowed_channels "
        "WHERE channel_key = ?",
        (channel_key,),
    )

    row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "channel_key": row[0],
        "channel_id": int(row[1]),
        "label": row[2],
        "allowed_roles": _parse_id_list(row[3]),
        "allowed_users": _parse_id_list(row[4]),
    }


async def add_allowed_channel(
    channel_key: str,
    channel_id: int,
    label: str,
    allowed_roles: list[str] | None = None,
    allowed_users: list[str] | None = None,
) -> None:
    db = _conn()

    async with _write_lock:
        await db.execute(
            "INSERT OR REPLACE INTO allowed_channels "
            "(channel_key, channel_id, label, allowed_roles, allowed_users) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                channel_key,
                str(channel_id),
                label,
                _dump_id_list(allowed_roles),
                _dump_id_list(allowed_users),
            ),
        )
        await db.commit()


async def remove_allowed_channel(channel_key: str) -> None:
    db = _conn()

    async with _write_lock:
        await db.execute(
            "DELETE FROM allowed_channels WHERE channel_key = ?",
            (channel_key,),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Saved messages (mensajes cog)
# ---------------------------------------------------------------------------

async def add_saved_message(author_id: int, content: str) -> int:
    """Inserts a saved message and returns its new id."""
    db = _conn()

    async with _write_lock:
        cur = await db.execute(
            "INSERT INTO saved_messages (author_id, content, created_at) "
            "VALUES (?, ?, ?)",
            (str(author_id), content, datetime.datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cur.lastrowid


async def get_saved_messages() -> list[dict[str, Any]]:
    """Returns all saved messages in insertion order."""
    db = _conn()

    cursor = await db.execute(
        "SELECT id, author_id, content FROM saved_messages ORDER BY id"
    )
    rows = await cursor.fetchall()

    return [
        {"id": row[0], "author_id": int(row[1]), "content": row[2]}
        for row in rows
    ]


async def get_saved_message(message_id: int) -> dict[str, Any] | None:
    db = _conn()

    cursor = await db.execute(
        "SELECT id, author_id, content FROM saved_messages WHERE id = ?",
        (message_id,),
    )
    row = await cursor.fetchone()

    if row is None:
        return None

    return {"id": row[0], "author_id": int(row[1]), "content": row[2]}


async def update_saved_message(message_id: int, content: str) -> None:
    db = _conn()

    async with _write_lock:
        await db.execute(
            "UPDATE saved_messages SET content = ? WHERE id = ?",
            (content, message_id),
        )
        await db.commit()


async def delete_saved_message(message_id: int) -> None:
    db = _conn()

    async with _write_lock:
        await db.execute(
            "DELETE FROM saved_messages WHERE id = ?",
            (message_id,),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Dashboard config (kill switch, etc — simple key/value store)
# ---------------------------------------------------------------------------

async def get_config(
    key: str,
    default: str | None = None,
) -> str | None:
    db = _conn()

    cursor = await db.execute(
        "SELECT value FROM dashboard_config WHERE key = ?",
        (key,),
    )

    row = await cursor.fetchone()

    return row[0] if row else default


async def set_config(
    key: str,
    value: str,
) -> None:
    db = _conn()

    async with _write_lock:
        await db.execute(
            "INSERT INTO dashboard_config (key, value) "
            "VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "value = excluded.value",
            (key, value),
        )
        await db.commit()


async def is_sending_enabled() -> bool:
    value = await get_config(
        "sending_enabled",
        default="true",
    )
    return value == "true"


async def set_sending_enabled(enabled: bool) -> None:
    await set_config(
        "sending_enabled",
        "true" if enabled else "false",
    )


# ---------------------------------------------------------------------------
# API key (managed from the admin panel; source of truth for /api/* auth)
# ---------------------------------------------------------------------------

async def get_api_key() -> str | None:
    """Return the dashboard-managed API key, or None if none is set."""
    value = await get_config("goonbot_api_key", default=None)
    return value if value else None


async def get_api_key_created_at() -> str | None:
    """ISO timestamp of when the current API key was generated."""
    return await get_config("goonbot_api_key_created_at", default=None)


async def set_api_key(key: str) -> None:
    """Store a new API key, stamping its creation time."""
    await set_config("goonbot_api_key", key)
    await set_config(
        "goonbot_api_key_created_at",
        datetime.datetime.utcnow().isoformat(),
    )


async def clear_api_key() -> None:
    """Revoke the current API key."""
    await set_config("goonbot_api_key", "")
    await set_config("goonbot_api_key_created_at", "")


async def ensure_api_key_seeded() -> None:
    """Seed the panel-managed key from GOONBOT_API_KEY on first run.

    After this the admin panel is the source of truth; the env var only keeps
    working if it still matches the panel's current key.
    """
    if await get_api_key() is None:
        env_key = os.getenv("GOONBOT_API_KEY")
        if env_key:
            await set_api_key(env_key)
