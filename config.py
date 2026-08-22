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

# ---------------------------------------------------------------------------
# RNG module (Sol's RNG-style gacha)
# ---------------------------------------------------------------------------

# Custom emoji for the GoonBot Token. Paste the emoji ID here once you create
# it in your server, e.g. "<:goonbot:123456789012345678>".
GOONBOT_TOKEN_EMOJI = os.getenv("GOONBOT_TOKEN_EMOJI", "<:gooncoin:1540737207126597734>")

# Roll cooldowns and auto-roll window (seconds).
RNG_MANUAL_COOLDOWN = 15.0
RNG_AUTO_COOLDOWN = 6.7
RNG_AUTO_DURATION = 600.0  # 10 minutes of auto-roll per Auto-Goon

# Pity: every 100 pity points guarantees one tier above the last drop.
RNG_PITY_THRESHOLD = 100

# Tokens earned per roll (random in this range).
RNG_TOKENS_MIN = 1
RNG_TOKENS_MAX = 10

# Tiers ordered from most common to rarest: (name, "1 in N" odds, sell value).
# Sell value doubles as the duplicate auto-convert payout.
RNG_TIERS = [
    ("Folk", 2, 5),
    ("Son", 10, 25),
    ("Samaritano", 100, 100),
    ("Gitano", 500, 500),
    ("Final Boss", 2500, 2500),
    ("El Jefe", 25000, 12500),
    ("Goon Master", 250000, 100000),
    ("Seguito del GoonBot", 1000000, 1000000),
]

# Tiers that grant a Discord role + global announcement on drop (1 in 100k+).
RNG_ROLE_TIERS = {"Goon Master", "Seguito del GoonBot"}

# Recurring global events (luck multiplier windows). Each entry activates a
# multiplier event during its daily window; while active, all players get the
# multiplier. Multiple overlapping events stack (multiply together).
#
# Fields:
#   name       — shown in /rng event list and the /tokens luck breakdown
#   multiplier — luck multiplier applied to everyone while the window is open
#   weekday    — 0=Monday .. 6=Sunday, or None for every day
#   start_hour / end_hour — 24-hour clock; end_hour 24 = all day
#
# The draft below gives a daily 1.5x "happy hour" (18-21h) and a 2x all-day
# boost on weekends. Weekend evenings stack both (1.5 x 2 = 3x luck).
# Remove or edit entries freely.
RNG_EVENTS_SCHEDULE = [
    {"name": "Happy Hour Goon", "multiplier": 1.5, "weekday": None, "start_hour": 18, "end_hour": 21},
    {"name": "Fin de Semana Goon", "multiplier": 2.0, "weekday": 5, "start_hour": 0, "end_hour": 24},
    {"name": "Fin de Semana Goon", "multiplier": 2.0, "weekday": 6, "start_hour": 0, "end_hour": 24},
]

# Image URLs used by the bot (currently unused — kept here so they don't
# clutter main.py).
IMAGE_URLS = [
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745012944956/IMG_20251123_223528.jpg?ex=692578c2&is=69242742&hm=4b47769727c1751c0f1af171968e04cbe134e6c494a87811b7d6c1044d49b7e2",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745344426136/IMG_20251123_223600.jpg?ex=692578c2&is=69242742&hm=2abd81e14fc934758414968a69baf6f4eca971f094adabc7a9cfc37b44da663",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745986285749/IMG_20251123_223634.jpg?ex=692578c2&is=69242742&hm=115629a925ba57951db272b46001940669e6d2928b077d192ffa50d80244afb",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267746334281851/IMG_20251123_223645.jpg?ex=692578c2&is=69242742&hm=829b1eb7f7225568105da7bd020a57aec8d43dacb225e8e5c4f0a8a6d935fec",
    "https://cdn.discordapp.com/attachments/1417592875214176447/1442267745650606171/IMG_20251123_223622.jpg?ex=692578c2&is=69242742&hm=9a6666d6599e93084ac9dd010bcc8bcb8301ca2dd88191f1112ce061da66b7b",
]
