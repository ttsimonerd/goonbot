"""Print every stored song in the bot's music collection.

Run on the server (inside the bot's environment) with:

    python3 list_songs.py

It reads the same database as the bot (GOONBOT_DB_PATH, default
``data/goonbot.db``), so run it where that file lives.
"""

import os
import sqlite3

DB_PATH = os.getenv("GOONBOT_DB_PATH", "data/goonbot.db")

LABELS = {
    "spotify": "Spotify",
    "youtube": "YouTube",
    "soundcloud": "SoundCloud",
    "apple_music": "Apple Music",
    "deezer": "Deezer",
    "bandcamp": "Bandcamp",
    "other": "Otra plataforma",
}


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, title, artist, platform, owner_id, elo, normalized_url "
        "FROM music_songs WHERE deleted_at IS NULL ORDER BY id"
    ).fetchall()
    conn.close()

    if not rows:
        print("No hay canciones guardadas.")
        return

    print(f"{len(rows)} canciones guardadas:\n")
    for song_id, title, artist, platform, owner_id, elo, url in rows:
        label = LABELS.get(platform, platform or "?")
        print(f"#{song_id} · {title} — {artist} · {label} · ELO {elo} · dueño {owner_id}")
        print(f"     {url}")


if __name__ == "__main__":
    main()
