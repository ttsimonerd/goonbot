import os

# The server the dashboard checks membership against.
GUILD_ID = int(os.getenv("GUILD_ID", "1417556208767733823"))

# The only Discord user allowed into admin views/commands (moderation log,
# channel management, kill switch, los_horrores).
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "988470489909432334"))

# Full public URL the dashboard is served at (Coolify domain). Used to build
# the OAuth2 redirect_uri explicitly rather than trusting proxy headers.
DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Bot secrets / endpoints (moved out of main.py to keep it lean).
# ---------------------------------------------------------------------------

# Webhook the /redeploy command POSTs to, and its password.
WEBHOOK_URL = os.getenv("WEBHOOK_DEP")
REDEPLOY_PASSWORD = os.getenv("REDEPLOY_PASSWORD")

# Password for the destructive /los_horrores command (cogs/admin.py).
NUKE_PASSWORD = os.getenv("NUKE_PASSWORD")

# Image URLs used by the bot (currently unused — kept here so they don't
# clutter main.py).
IMAGE_URLS = [
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745012944956/IMG_20251123_223528.jpg?ex=692578c2&is=69242742&hm=4b47769727c1751c0f1af171968e04cbe134e6c494a87811b7d6c1044d49b7e2",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745344426136/IMG_20251123_223600.jpg?ex=692578c2&is=69242742&hm=2abd81e14fc934758414968a69baf6f4eca971f094adabc7a9cfc37b44da663",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745986285749/IMG_20251123_223634.jpg?ex=692578c2&is=69242742&hm=115629a925ba57951db272b46001940669e6d2928b077d192ffa50d80244afb",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267746334281851/IMG_20251123_223645.jpg?ex=692578c2&is=69242742&hm=829b1eb7f7225568105da7bd020a57aec8d43dacb225e8e5c4f0a8a6d935fec",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745650606171/IMG_20251123_223622.jpg?ex=692578c2&is=69242742&hm=9a6666d6599e93084ac9dd010bcc8bcb8301ca2dd88191f1112ce061da66b7b",
]
