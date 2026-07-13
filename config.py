import os

# The server the dashboard checks membership against.
GUILD_ID = int(os.getenv("GUILD_ID", "1417556208767733823"))

# The only Discord user allowed into admin views/commands (moderation log,
# channel management, kill switch, los_horrores).
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "988470489909432334"))

# Full public URL the dashboard is served at (Coolify domain). Used to build
# the OAuth2 redirect_uri explicitly rather than trusting proxy headers.
DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL", "http://localhost:8000")
