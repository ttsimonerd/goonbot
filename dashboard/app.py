"""
Dashboard web app. Runs inside the same process as the Discord bot (see
main.py), so it reaches Discord/economy state through direct function and
object access — db.py calls and the live `bot` instance — rather than a
separate internal HTTP API. No bot token duplication, no network hop.

create_app() is a factory (not a module-level `app = FastAPI()`) because it
needs the running bot instance injected, which only exists once main.py
constructs it.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from dashboard.limiter import limiter
from dashboard.routes import router as dashboard_router

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app(bot) -> FastAPI:
    app = FastAPI(title="GoonBot Dashboard")
    app.state.bot = bot

    session_secret = os.getenv("SESSION_SECRET")
    if not session_secret:
        raise RuntimeError(
            "SESSION_SECRET is not set — required for signed session cookies. "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
    app.add_middleware(SessionMiddleware, secret_key=session_secret, same_site="lax", https_only=True)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    static_dir = BASE_DIR / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/health")
    async def health() -> PlainTextResponse:
        # Coolify/Docker healthcheck target — deliberately says nothing about
        # bot connection state, just that the web process itself is alive.
        return PlainTextResponse("ok")

    app.include_router(dashboard_router)

    return app
