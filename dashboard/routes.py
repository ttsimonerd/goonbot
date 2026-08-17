"""Dashboard HTTP routes.

Everything here runs inside the same process as the Discord bot (see
main.py), so it reaches Discord and economy state through direct calls to
``db`` and the live ``bot`` instance rather than a separate internal API.
"""

import datetime
import logging
import secrets
from pathlib import Path
from typing import Any

import discord
from fastapi import APIRouter, Body, Form, Header, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

import db
from config import ADMIN_USER_ID, DASHBOARD_BASE_URL, GUILD_ID
from dashboard.auth import avatar_url, oauth
from dashboard.csrf import get_or_create_csrf_token, verify_csrf_token
from dashboard.limiter import limiter
from dashboard.membership import check_membership

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

MAX_MESSAGE_LENGTH = 500
ADMIN_LOG_PAGE_SIZE = 50

# request.session["user"] payload shape.
SessionUser = dict[str, str]


def _format_ts(iso: str) -> str:
    """Format an ISO timestamp into a short chat-friendly string (UTC)."""
    try:
        dt = datetime.datetime.fromisoformat(iso)
        return dt.strftime("%d %b %H:%M")
    except (ValueError, TypeError):
        return iso


def _legal_last_updated() -> str:
    """Return the 'Last updated' date shown on the legal pages.

    Uses the latest modification time of the terms/privacy templates, so the
    date updates automatically on every deploy instead of being hardcoded.
    """
    templates_dir = Path(__file__).resolve().parent / "templates"
    mtimes: list[float] = []
    for name in ("terms.html", "privacy.html"):
        try:
            mtimes.append((templates_dir / name).stat().st_mtime)
        except OSError:
            continue
    if not mtimes:
        return "unknown"
    latest = datetime.datetime.fromtimestamp(max(mtimes), tz=datetime.timezone.utc)
    return latest.strftime("%B %d, %Y")


def can_send_to_channel(
    member: discord.Member,
    channel: discord.abc.GuildChannel | None,
    channel_info: dict[str, Any],
) -> bool:
    """Decide whether a member may make the bot post to a channel.

    Admin always may. Everyone else must (a) be able to send in that channel
    in Discord itself — the automatic role/user mapping — and, if the channel
    has a manual allowlist, (b) match it via their user ID or one of their
    roles.
    """
    if member.id == ADMIN_USER_ID:
        return True

    if channel is None:
        return False

    if not channel.permissions_for(member).send_messages:
        return False

    allowed_roles = channel_info.get("allowed_roles") or []
    allowed_users = channel_info.get("allowed_users") or []
    if allowed_roles or allowed_users:
        if str(member.id) in allowed_users:
            return True
        member_roles = {str(role.id) for role in member.roles}
        return bool(member_roles.intersection(allowed_roles))

    return True


def _resolve_role_names(guild: discord.Guild | None, ids: list[str]) -> list[str]:
    """Map role IDs to human-readable names (falls back to the ID)."""
    if guild is None:
        return ids
    names: list[str] = []
    for role_id in ids:
        role = guild.get_role(int(role_id))
        names.append(role.name if role else f"ID {role_id}")
    return names


def _resolve_member_names(guild: discord.Guild | None, ids: list[str]) -> list[str]:
    """Map user IDs to display names from the member cache (falls back to ID)."""
    if guild is None:
        return ids
    names: list[str] = []
    for user_id in ids:
        member = guild.get_member(int(user_id))
        names.append(member.display_name if member else f"ID {user_id}")
    return names


def _member_label(member: discord.Member) -> str:
    """Human-friendly label for the member dropdown."""
    if member.display_name != member.name:
        return f"{member.display_name} (@{member.name})"
    return member.display_name


async def get_current_member(
    request: Request,
) -> tuple[SessionUser | None, discord.Member | None]:
    """Return (session_user, live_member) or (None, None).

    Re-validates membership via ``check_membership()`` — cache lookup first,
    with a ``fetch_member()`` fallback — so access is revoked the moment
    someone leaves the server, even if they aren't in the member cache.

    Also ensures a ``dashboard_users`` row exists — defensive, in case a
    session ever outlives its corresponding DB row (e.g. it was cleared
    manually).
    """
    user = request.session.get("user")
    if not user:
        return None, None
    bot = request.app.state.bot
    is_member, member = await check_membership(bot, int(user["discord_id"]))
    if not is_member or member is None:
        request.session.clear()
        return None, None
    await db.upsert_dashboard_user(
        int(user["discord_id"]), user["username"], user["avatar_url"]
    )
    return user, member


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    """Start the Discord OAuth2 flow."""
    redirect_uri = f"{DASHBOARD_BASE_URL}/auth/callback"
    return await oauth.discord.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback")
@limiter.limit("10/minute")
async def auth_callback(request: Request) -> Response:
    """Exchange the OAuth code for a token, verify membership, and log in.

    On any OAuth/profile failure we bounce back to the landing page with an
    ``error`` query param instead of letting the catch-all return a raw 500.
    """
    try:
        token = await oauth.discord.authorize_access_token(request)
        resp = await oauth.discord.get("users/@me", token=token)
        profile = resp.json()
        discord_id = int(profile["id"])
    except Exception as exc:
        logger.error(
            "OAuth callback failed",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return RedirectResponse(url="/?error=oauth", status_code=303)

    bot = request.app.state.bot
    is_member, member = await check_membership(bot, discord_id)
    if not is_member or member is None:
        guild = bot.get_guild(GUILD_ID)
        guild_name = guild.name if guild else "the server"
        return templates.TemplateResponse(
            request,
            "denied.html",
            {"guild_name": guild_name},
        )

    username = member.display_name
    avatar = avatar_url(profile["id"], profile.get("avatar"))

    await db.upsert_dashboard_user(discord_id, username, avatar)
    request.session["user"] = {
        "discord_id": str(discord_id),
        "username": username,
        "avatar_url": avatar,
    }
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session cookie and return to the landing page."""
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@router.get("/terms")
async def terms(request: Request) -> Response:
    """Render the public Terms of Service page."""
    user, _member = await get_current_member(request)
    is_admin = bool(user) and int(user["discord_id"]) == ADMIN_USER_ID
    return templates.TemplateResponse(
        request,
        "terms.html",
        {"user": user, "is_admin": is_admin, "last_updated": _legal_last_updated()},
    )


@router.get("/privacy")
async def privacy(request: Request) -> Response:
    """Render the public Privacy Policy page."""
    user, _member = await get_current_member(request)
    is_admin = bool(user) and int(user["discord_id"]) == ADMIN_USER_ID
    return templates.TemplateResponse(
        request,
        "privacy.html",
        {"user": user, "is_admin": is_admin, "last_updated": _legal_last_updated()},
    )


@router.get("/")
async def dashboard_home(request: Request) -> Response:
    """Render the logged-in dashboard (or the login page if unauthenticated)."""
    user, member = await get_current_member(request)
    if not user or member is None:
        return templates.TemplateResponse(request, "login.html", {})

    discord_id = int(user["discord_id"])
    bot = request.app.state.bot
    economy = await db.get_user(GUILD_ID, discord_id)
    dash_user = await db.get_dashboard_user(discord_id)
    recent_messages = [
        {**m, "sent_at_short": _format_ts(m["sent_at"])}
        for m in reversed(await db.get_recent_messages(discord_id, limit=10))
    ]
    allowed_channels = [
        ch
        for ch in await db.get_allowed_channels()
        if can_send_to_channel(member, bot.get_channel(ch["channel_id"]), ch)
    ]
    sending_enabled = await db.is_sending_enabled()
    csrf_token = get_or_create_csrf_token(request)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "coins": economy["money"],
            "messages_remaining": dash_user["messages_remaining"],
            "daily_limit": db.DAILY_MESSAGE_LIMIT,
            "recent_messages": recent_messages,
            "allowed_channels": allowed_channels,
            "sending_enabled": sending_enabled,
            "csrf_token": csrf_token,
            "is_admin": discord_id == ADMIN_USER_ID,
        },
    )


@router.post("/send")
@limiter.limit("10/minute")
async def send_message(
    request: Request,
    channel_key: str = Form(...),
    content: str = Form(...),
    csrf_token: str = Form(...),
) -> RedirectResponse:
    """Validate and deliver a user's message to the chosen channel."""
    user, member = await get_current_member(request)
    if not user or member is None:
        return RedirectResponse(url="/", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        return RedirectResponse(url="/?error=csrf", status_code=303)

    if not await db.is_sending_enabled():
        return RedirectResponse(url="/?error=disabled", status_code=303)

    dash_user = await db.get_dashboard_user(int(user["discord_id"]))
    if dash_user["messages_remaining"] <= 0:
        return RedirectResponse(url="/?error=limit", status_code=303)

    content = content.strip()
    if not content or len(content) > MAX_MESSAGE_LENGTH:
        return RedirectResponse(url="/?error=invalid", status_code=303)

    channel_info = await db.get_allowed_channel(channel_key)
    if channel_info is None:
        return RedirectResponse(url="/?error=invalid_channel", status_code=303)

    bot = request.app.state.bot
    channel = bot.get_channel(channel_info["channel_id"])
    if channel is None:
        return RedirectResponse(url="/?error=channel_unavailable", status_code=303)

    if not can_send_to_channel(member, channel, channel_info):
        return RedirectResponse(url="/?error=forbidden", status_code=303)

    try:
        await channel.send(content)
    except discord.HTTPException as exc:
        logger.error(
            "Failed to send dashboard message to channel %s",
            channel_info["channel_id"],
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return RedirectResponse(url="/?error=send_failed", status_code=303)

    await db.log_message(int(user["discord_id"]), channel_key, content)
    await db.increment_messages_used(int(user["discord_id"]))

    return RedirectResponse(url="/?sent=1", status_code=303)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

async def require_admin(request: Request) -> SessionUser | None:
    """Return the session user if they are the configured admin, else None.

    Non-admins get ``None`` and are redirected away by the caller.
    """
    user, _member = await get_current_member(request)
    if not user or int(user["discord_id"]) != ADMIN_USER_ID:
        return None
    return user


@router.get("/admin")
async def admin_home(request: Request, page: int = 1) -> Response:
    """Render the admin panel with a paginated message log."""
    user = await require_admin(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)

    page = max(1, page)
    offset = (page - 1) * ADMIN_LOG_PAGE_SIZE

    logs = await db.get_all_message_logs(limit=ADMIN_LOG_PAGE_SIZE, offset=offset)
    total = await db.count_message_logs()
    total_pages = max(1, (total + ADMIN_LOG_PAGE_SIZE - 1) // ADMIN_LOG_PAGE_SIZE)
    channels = await db.get_allowed_channels()
    bot = request.app.state.bot
    guild = bot.get_guild(GUILD_ID)

    guild_channels: list[dict[str, Any]] = []
    guild_roles: list[dict[str, Any]] = []
    guild_members: list[dict[str, Any]] = []
    if guild is not None:
        guild_channels = sorted(
            ({"id": ch.id, "name": ch.name} for ch in guild.text_channels),
            key=lambda c: c["name"].lower(),
        )
        guild_roles = sorted(
            (
                {"id": role.id, "name": role.name}
                for role in guild.roles
                if role.name != "@everyone"
            ),
            key=lambda r: r["name"].lower(),
        )
        guild_members = sorted(
            (
                {"id": m.id, "name": _member_label(m)}
                for m in guild.members
                if not m.bot
            ),
            key=lambda m: m["name"].lower(),
        )

    for ch in channels:
        ch["allowed_roles_names"] = _resolve_role_names(guild, ch["allowed_roles"])
        ch["allowed_users_names"] = _resolve_member_names(guild, ch["allowed_users"])

    sending_enabled = await db.is_sending_enabled()
    csrf_token = get_or_create_csrf_token(request)

    api_key = await db.get_api_key()
    api_key_created_at = await db.get_api_key_created_at()
    # Pop the one-time key shown after generation; the template only renders
    # it on the request immediately following the redirect.
    generated_key = request.session.pop("generated_api_key", None)

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": user,
            "is_admin": True,
            "logs": logs,
            "channels": channels,
            "sending_enabled": sending_enabled,
            "csrf_token": csrf_token,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "api_key_masked": ("••••" + api_key[-4:]) if api_key else None,
            "api_key_created_at": api_key_created_at,
            "generated_key": generated_key,
            "guild_channels": guild_channels,
            "guild_roles": guild_roles,
            "guild_members": guild_members,
        },
    )


@router.post("/admin/channels/add")
@limiter.limit("20/minute")
async def admin_add_channel(
    request: Request,
    channel_key: str = Form(...),
    channel_id: str = Form(...),
    label: str = Form(...),
    allowed_roles: list[str] = Form(default=[]),
    allowed_users: list[str] = Form(default=[]),
    csrf_token: str = Form(...),
) -> RedirectResponse:
    """Add an allowed channel with an optional role/user allowlist (admin only)."""
    user = await require_admin(request)
    if not user or not verify_csrf_token(request, csrf_token):
        return RedirectResponse(url="/", status_code=303)

    channel_key = channel_key.strip().lower().replace(" ", "_")
    if not channel_key or not channel_id.strip().isdigit() or not label.strip():
        return RedirectResponse(
            url="/admin?error=invalid_channel_form", status_code=303
        )

    await db.add_allowed_channel(
        channel_key,
        int(channel_id.strip()),
        label.strip(),
        allowed_roles=[
            str(r).strip() for r in allowed_roles if str(r).strip().isdigit()
        ],
        allowed_users=[
            str(u).strip() for u in allowed_users if str(u).strip().isdigit()
        ],
    )
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/channels/remove")
@limiter.limit("20/minute")
async def admin_remove_channel(
    request: Request,
    channel_key: str = Form(...),
    csrf_token: str = Form(...),
) -> RedirectResponse:
    """Remove an allowed channel (admin only)."""
    user = await require_admin(request)
    if not user or not verify_csrf_token(request, csrf_token):
        return RedirectResponse(url="/", status_code=303)

    await db.remove_allowed_channel(channel_key)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/kill-switch")
@limiter.limit("20/minute")
async def admin_kill_switch(
    request: Request,
    enabled: str = Form(...),
    csrf_token: str = Form(...),
) -> RedirectResponse:
    """Toggle the dashboard message-sending kill switch (admin only)."""
    user = await require_admin(request)
    if not user or not verify_csrf_token(request, csrf_token):
        return RedirectResponse(url="/", status_code=303)

    await db.set_sending_enabled(enabled == "true")
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/api-key/generate")
@limiter.limit("10/minute")
async def admin_generate_api_key(
    request: Request,
    csrf_token: str = Form(...),
    confirm: str | None = Form(None),
) -> RedirectResponse:
    """Generate and store a new API key, showing it to the admin once."""
    user = await require_admin(request)
    if not user or not verify_csrf_token(request, csrf_token):
        return RedirectResponse(url="/", status_code=303)

    if confirm != "on":
        return RedirectResponse(url="/admin?error=confirm_required", status_code=303)

    new_key = "gb_" + secrets.token_urlsafe(32)
    await db.set_api_key(new_key)
    request.session["generated_api_key"] = new_key
    return RedirectResponse(url="/admin?key_generated=1", status_code=303)


@router.post("/admin/api-key/revoke")
@limiter.limit("10/minute")
async def admin_revoke_api_key(
    request: Request,
    csrf_token: str = Form(...),
    confirm: str | None = Form(None),
) -> RedirectResponse:
    """Revoke the current API key, disabling /api/* auth until a new one is set."""
    user = await require_admin(request)
    if not user or not verify_csrf_token(request, csrf_token):
        return RedirectResponse(url="/", status_code=303)

    if confirm != "on":
        return RedirectResponse(url="/admin?error=confirm_required", status_code=303)

    await db.clear_api_key()
    return RedirectResponse(url="/admin?key_revoked=1", status_code=303)


# ---------------------------------------------------------------------------
# Machine-to-machine API
# ---------------------------------------------------------------------------

async def authenticate_api_key(x_api_key: str | None) -> None:
    """Raise HTTPException unless the header matches the panel-managed key."""
    expected_key = await db.get_api_key()
    if expected_key is None:
        raise HTTPException(
            status_code=503,
            detail="No API key configured. Generate one in the admin panel.",
        )
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/api/member/exists")
async def member_exists(
    request: Request,
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Report whether a Discord user is a member of the guild.

    Authenticated via the ``X-Api-Key`` header against the panel-managed API
    key (seeded from ``GOONBOT_API_KEY`` on first run). The body is marked
    with ``Body(...)`` so FastAPI actually parses the JSON payload (a bare
    ``dict`` parameter would be treated as a query param instead).
    """
    await authenticate_api_key(x_api_key)

    bot = request.app.state.bot
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        raise HTTPException(status_code=503, detail="Guild not available")

    try:
        discord_id = int(body["discordUserId"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid discordUserId")

    # Cache lookup first, then a direct API lookup as fallback.
    is_member, member = await check_membership(bot, discord_id)
    if not is_member or member is None:
        return {"exists": False}

    return {
        "exists": True,
        "id": member.id,
        "username": member.name,
        "display_name": member.display_name,
        "bot": member.bot,
    }


@router.get("/api/status")
async def api_status(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return bot/guild health info. Authenticated via ``X-Api-Key``."""
    await authenticate_api_key(x_api_key)

    bot = request.app.state.bot
    guild = bot.get_guild(GUILD_ID)

    latency = bot.latency
    latency_ms = (
        round(latency * 1000)
        if (latency is not None and 0 < latency < 60)
        else None
    )

    return {
        "status": "ok",
        "bot": {
            "connected": bot.is_ready(),
            "latency_ms": latency_ms,
            "user": str(bot.user) if bot.user else None,
        },
        "guild": {
            "available": guild is not None,
            "name": guild.name if guild else None,
            "member_count": guild.member_count if guild else None,
        },
    }
