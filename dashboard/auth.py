"""
Discord OAuth2 login (`identify` scope only — we don't request `guilds`
because membership is checked via the live bot object instead, see
check_membership() in app.py).
"""

import os

from authlib.integrations.starlette_client import OAuth

oauth = OAuth()
oauth.register(
    name="discord",
    client_id=os.getenv("DISCORD_CLIENT_ID"),
    client_secret=os.getenv("DISCORD_CLIENT_SECRET"),
    access_token_url="https://discord.com/api/oauth2/token",
    authorize_url="https://discord.com/api/oauth2/authorize",
    api_base_url="https://discord.com/api/",
    client_kwargs={"scope": "identify"},
)


def avatar_url(discord_id: str, avatar_hash: str | None) -> str:
    if avatar_hash:
        ext = "gif" if avatar_hash.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.{ext}"
    # Discord's default avatar, deterministic per-user
    default_index = (int(discord_id) >> 22) % 6
    return f"https://cdn.discordapp.com/embed/avatars/{default_index}.png"
