from pathlib import Path

import discord
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import db
from config import ADMIN_USER_ID, DASHBOARD_BASE_URL, GUILD_ID
from dashboard.auth import avatar_url, oauth
from dashboard.csrf import get_or_create_csrf_token, verify_csrf_token
from dashboard.limiter import limiter
from dashboard.membership import check_membership

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

MAX_MESSAGE_LENGTH = 500


async def get_current_member(request: Request):
    """Returns (session_user, live_member) or (None, None). Re-validates
    membership against the bot's in-memory cache on every call (cheap, no
    API request) so someone who left the server loses access immediately.

    Also ensures a dashboard_users row exists — defensive, in case a session
    ever outlives its corresponding DB row (e.g. it was cleared manually)."""
    user = request.session.get("user")
    if not user:
        return None, None
    bot = request.app.state.bot
    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(int(user["discord_id"])) if guild else None
    if member is None:
        request.session.clear()
        return None, None
    await db.upsert_dashboard_user(int(user["discord_id"]), user["username"], user["avatar_url"])
    return user, member


@router.get("/login")
async def login(request: Request):
    redirect_uri = f"{DASHBOARD_BASE_URL}/auth/callback"
    return await oauth.discord.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.discord.authorize_access_token(request)
    resp = await oauth.discord.get("users/@me", token=token)
    profile = resp.json()

    discord_id = int(profile["id"])
    bot = request.app.state.bot
    is_member, member = await check_membership(bot, discord_id)
    if not is_member:
        return templates.TemplateResponse(
            request, "denied.html", {"guild_name": bot.get_guild(GUILD_ID).name if bot.get_guild(GUILD_ID) else "the server"}
        )

    username = member.display_name
    avatar = avatar_url(profile["id"], profile.get("avatar"))

    await db.upsert_dashboard_user(discord_id, username, avatar)
    request.session["user"] = {"discord_id": str(discord_id), "username": username, "avatar_url": avatar}
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@router.get("/")
async def dashboard_home(request: Request):
    user, member = await get_current_member(request)
    if not user:
        return templates.TemplateResponse(request, "login.html", {})

    economy = await db.get_user(GUILD_ID, int(user["discord_id"]))
    dash_user = await db.get_dashboard_user(int(user["discord_id"]))
    recent_messages = await db.get_recent_messages(int(user["discord_id"]), limit=5)
    allowed_channels = await db.get_allowed_channels()
    sending_enabled = await db.is_sending_enabled()
    csrf_token = get_or_create_csrf_token(request)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "coins": economy["money"],
            "messages_remaining": dash_user["messages_remaining"],
            "recent_messages": recent_messages,
            "allowed_channels": allowed_channels,
            "sending_enabled": sending_enabled,
            "csrf_token": csrf_token,
            "is_admin": int(user["discord_id"]) == ADMIN_USER_ID,
        },
    )


@router.post("/send")
@limiter.limit("10/minute")
async def send_message(
    request: Request,
    channel_key: str = Form(...),
    content: str = Form(...),
    csrf_token: str = Form(...),
):
    user, member = await get_current_member(request)
    if not user:
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

    try:
        await channel.send(content)
    except discord.HTTPException:
        return RedirectResponse(url="/?error=send_failed", status_code=303)

    await db.log_message(int(user["discord_id"]), channel_key, content)
    await db.increment_messages_used(int(user["discord_id"]))

    return RedirectResponse(url="/?sent=1", status_code=303)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

async def require_admin(request: Request):
    user, member = await get_current_member(request)
    if not user or int(user["discord_id"]) != ADMIN_USER_ID:
        return None
    return user


@router.get("/admin")
async def admin_home(request: Request):
    user = await require_admin(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)

    logs = await db.get_all_message_logs(limit=100)
    channels = await db.get_allowed_channels()
    sending_enabled = await db.is_sending_enabled()
    csrf_token = get_or_create_csrf_token(request)

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": user,
            "logs": logs,
            "channels": channels,
            "sending_enabled": sending_enabled,
            "csrf_token": csrf_token,
        },
    )


@router.post("/admin/channels/add")
async def admin_add_channel(
    request: Request,
    channel_key: str = Form(...),
    channel_id: str = Form(...),
    label: str = Form(...),
    csrf_token: str = Form(...),
):
    user = await require_admin(request)
    if not user or not verify_csrf_token(request, csrf_token):
        return RedirectResponse(url="/", status_code=303)

    channel_key = channel_key.strip().lower().replace(" ", "_")
    if not channel_key or not channel_id.strip().isdigit() or not label.strip():
        return RedirectResponse(url="/admin?error=invalid_channel_form", status_code=303)

    await db.add_allowed_channel(channel_key, int(channel_id.strip()), label.strip())
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/channels/remove")
async def admin_remove_channel(
    request: Request,
    channel_key: str = Form(...),
    csrf_token: str = Form(...),
):
    user = await require_admin(request)
    if not user or not verify_csrf_token(request, csrf_token):
        return RedirectResponse(url="/", status_code=303)

    await db.remove_allowed_channel(channel_key)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/kill-switch")
async def admin_kill_switch(
    request: Request,
    enabled: str = Form(...),
    csrf_token: str = Form(...),
):
    user = await require_admin(request)
    if not user or not verify_csrf_token(request, csrf_token):
        return RedirectResponse(url="/", status_code=303)

    await db.set_sending_enabled(enabled == "true")
    return RedirectResponse(url="/admin", status_code=303)
