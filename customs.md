# GoonBot — Customization Map

Everything in the project that is tunable, configurable, or meant to be
edited. Organized by file with **file:line** references so you can jump
straight to the spot.

> **Heads up:** line numbers shift whenever you edit a file above them.
> Treat them as search hints — `Ctrl+F` the constant/variable name if a
> reference no longer matches.

---

## 1. Environment variables (deploy-time)

Set these in your hosting panel / `docker-compose` env — **no code edit needed**.

| Variable | Read at | Default | What it does |
|---|---|---|---|
| `DISCORD_TOKEN` | `main.py` (`main()`) | — | Bot token (required) |
| `GUILD_ID` | `config.py:4` | `1417556208767733823` | The server the bot syncs commands to / checks membership against |
| `ADMIN_USER_ID` | `config.py:8` | `988470489909432334` | Only user allowed in admin views/commands |
| `DASHBOARD_BASE_URL` | `config.py:12` | `http://localhost:8000` | Public dashboard URL (OAuth redirect) |
| `WEBHOOK_DEP` | `config.py:19` | — | Webhook that `/redeploy` POSTs to |
| `REDEPLOY_PASSWORD` | `config.py:20` | — | Password for `/redeploy` |
| `NUKE_PASSWORD` | `config.py:23` | — | Password for `/los_horrores` |
| `GOONBOT_TOKEN_EMOJI` | `config.py:31` | `<:goonbot:PUT_EMOJI_ID_HERE>` | **Your GoonBot Token emoji — paste the ID here** |
| `GOONBOT_DB_PATH` | `db.py:23` | `data/goonbot.db` | Where the SQLite DB lives (keep in a mounted volume) |
| `GOONBOT_API_KEY` | `db.py` (`ensure_api_key_seeded`) | — | Seeds the dashboard-managed API key (panel is source of truth after) |
| `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` | `dashboard/auth.py:19–20` | — | Dashboard Discord OAuth app |
| `SESSION_SECRET` | `dashboard/app.py:38` | — | Signs dashboard session cookies (required) |
| `PORT` | `main.py:411` | `8000` | Dashboard/bot HTTP port |
| `AUDIO_DIR` | `cogs/soundboard.py:10` | `audio/` | Folder with the soundboard files |

---

## 2. `config.py` — RNG game balance (the fun part)

| Lines | Constant | Tunable |
|---|---|---|
| `31` | `GOONBOT_TOKEN_EMOJI` | The token emoji (see env table) |
| `34` | `RNG_MANUAL_COOLDOWN` | Seconds between manual `/roll` (15) |
| `35` | `RNG_AUTO_COOLDOWN` | Seconds between auto-rolls (6.7) |
| `36` | `RNG_AUTO_DURATION` | How long one Auto-Goon lasts (600 s = 10 min) |
| `39` | `RNG_PITY_THRESHOLD` | Pity points needed for a guaranteed tier-up (100) |
| `42–43` | `RNG_TOKENS_MIN` / `RNG_TOKENS_MAX` | Tokens earned per roll (random 1–10) |
| `46` | `RNG_MULTIROLL_COUNT` | How many rolls a ×10 button runs (10) |
| `49–51` | `RNG_DAILY_BASE` / `RNG_DAILY_STREAK_BONUS` / `RNG_DAILY_CAP` | Daily login reward: base (20), +/streak day (10), cap (100) |
| `56–58` | `RNG_COMBO_WINDOW` / `RNG_COMBO_STEP` / `RNG_COMBO_CAP` | Roll streak combo: 2-min window, +5%/level, capped x2 (20 combo) |
| `62` | `RNG_SESSION_WINDOW` | Session stats idle window (600 s = 10 min) |
| `66–73` | `RNG_MISSIONS` | **Daily missions** — `(id, name, target, reward)`; 3 are picked per user per day |
| `74` | `RNG_MISSIONS_PER_DAY` | How many missions a user gets daily (3) |
| `78–102` | `RNG_CRAFT_RECIPES` | **Crafting recipes** — `materials` is `[[item_name, qty], ...]`, `product` is the result item name |
| `104–109` | `RNG_TIERS` | **The 8 tiers**: `(name, 1-in-N odds, sell value)` — edit odds or dupe/sell payouts |
| `111` | `RNG_ROLE_TIERS` | Which tiers grant a role + announcement (Goon Master, Seguito) |
| `126–131` | `RNG_EVENTS_SCHEDULE` | Recurring luck events — applied by the loop in `cogs/rng_engine.py` |
| `134` | `IMAGE_URLS` | Unused image list (kept out of main.py) |

---

## 3. `db.py` — data defaults & the item catalog

| Lines | Item | Tunable |
|---|---|---|
| `23` | `DB_PATH` | DB location (env override) |
| `328–364` | `RNG_ITEMS` | **The entire RNG item catalog** — one dict per item: `name`, `rarity_tier`, `base_odds`, `item_type` (EQUIPPABLE/CONSUMABLE/MATERIAL/RELIC), `description`, `icon_emoji`, `luck_multiplier` (aura passive), `shop_price` (NULL = not sold), `sell_value` (dupe/sale payout). Add/remove items here — seeding is idempotent |
| `510` | `DEFAULT_USER` | Gambling starting money (100) |
| `655–666` | `DEFAULT_SETTINGS` | Per-guild defaults: lockout hours (24), max warns (3), channel/role IDs |
| `820` | `DAILY_MESSAGE_LIMIT` | Dashboard messages per user per day (3) |

> The music system's schema lives in `SCHEMA` (`db.py:29–310`); settings columns are auto-migrated in `_migrate()` (`db.py:387`).

---

## 4. `main.py` — bot shell, intents, help

| Lines | Item | Tunable |
|---|---|---|
| `14–17` | `logging.basicConfig` | Log level + format |
| `24–25` | `intents.members` / `intents.message_content` | Privileged intents (must match Developer Portal) |
| `54–62` | `extensions` | Which cogs load — add/remove here |
| `195` | `command_prefix` | Legacy prefix (`^`, unused by slash commands) |
| `214–221` | `/ping` message | The "hosted on ttsmcz RPI5" text |
| `223–228` | `/qtfn` message | The meme reply |
| `230–360` | `/help` embed | **All help sections** — add your new commands here |
| `363+` | `/redeploy` | Deploy webhook command |
| `411` | `PORT` | HTTP port (env override) |

---

## 5. `cogs/music.py` — music economy & battles

| Lines | Constant | Tunable |
|---|---|---|
| `37` | `NORMAL_COOLDOWN` | Seconds between normal battles (60) |
| `38` | `RECLAIM_COOLDOWN` | Cooldown for reclaim battles (3 days) |
| `39` | `INITIAL_ELO` | Starting ELO for every song (1000) |
| `40–41` | `ELO_STEAL_FRACTION` / `ELO_STEAL_MIN` | Battle ELO steal: 50% of loser's ELO, minimum 100 |
| `42` | `EXTRACT_TIMEOUT` | Seconds before yt-dlp/Spotify extraction times out (45) |
| `45` | `SOTD_VOTE_WINDOW` | Song of the Day voting window (24 h) |
| `46–47` | `SOTD_BOOST_MIN` / `SOTD_BOOST_MAX` | SOTD winner bonus ELO (random 120–670) |
| `48` | `SOTD_MAX_WEEKLY` | Max times a song can be SOTD per week (2) |
| `51–66` | `lock_cooldown_seconds()` | Knockout lock tiers (1/2/3/5/7 days by ELO depth) |
| `72` | `_URL_RE` | URL detection regex |
| `76–86` | `MUSIC_DOMAINS` | Platforms auto-detected in the music channel |
| `116` | `PLATFORM_LABELS` | Display names per platform |
| `235–245` | `_SPOTIFY_*_RE` | Spotify page parsing regexes (advanced — only touch if Spotify breaks) |
| `273` | `_SPOTIFY_UA` | User-Agent used to fetch Spotify pages (mobile UA gets server-rendered metadata) |
| `327` | `requests timeout=15` | Spotify fetch timeout |
| `397`, `468` | `View(timeout=180)` | Battle/reclaim button views expire after 180 s |
| *throughout* | message strings | All embeds/replies are inline Spanish — edit freely |

---

## 6. `cogs/gambling.py` — economy games

| Lines | Item | Tunable |
|---|---|---|
| `20` | `format_money()` | How money is formatted |
| `118` | `predict_multiplier(days)` | Votebet multiplier formula |
| `122–123` | `predict_success_chance(days)` | Votebet success-chance formula |
| `400–417` | Roulette payouts | red/black/even/odd ×2, green ×35 |
| `575` | Blackjack payout | Blackjack pays `bet * 2.5` |
| `608` | Crash start | Initial multiplier `1.25` |
| `615` | Crash success chance | `max(0.15, 0.75 - 0.10*(round-1))` |
| `658` | Crash growth | Multiplier grows `+0.4 to +0.85` per round |
| `609` | Crash view timeout | 120 s |
| `844–845` | `/daily` reward | Base `random(25, 100)` + streak bonus `min(streak-1, 7) * 10` |
| *throughout* | message strings | All payout texts in Spanish/English mix |

---

## 7. `cogs/fun.py` — content lists

| Lines | List | Tunable |
|---|---|---|
| `18–26` | `roasts` | `/roast` insults — add your own |
| `36–38` | `grapes` | `/grape` messages (keep the joke tone) |
| `62` | `reaction_pool` | Emojis `/rampage` adds to the target's messages |
| `70–73` | history scan limits | `limit=200` messages scanned, stops at 20 of the target's |
| `79–82` | `ataques` | `/rampage` attack lines (`{user}` placeholder) |
| `91–99` | `gifs` | `/rampage` GIF URLs |

---

## 8. `cogs/soundboard.py` — sound playback

| Lines | Item | Tunable |
|---|---|---|
| `10` | `AUDIO_DIR` | Sound file folder (env override) |
| `12` | `FFMPEG_OPTIONS` | ffmpeg args (bitrate etc.) |
| `88`, `144` | volume | `/play` volume accepts 1–200, default 100 (clamped at line 144) |

---

## 9. Dashboard (`dashboard/`)

| Lines | Item | Tunable |
|---|---|---|
| `dashboard/auth.py:22` | OAuth scope | `identify` — add `guilds` etc. if you need more |
| `dashboard/routes.py:31` | `MAX_MESSAGE_LENGTH` | Max chars per dashboard message (500) |
| `dashboard/routes.py:162, 276, 424, 460, 476, 492, 513` | `@limiter.limit(...)` | Per-route rate limits (10 or 20 per minute) |
| `dashboard/app.py:38` | `SESSION_SECRET` | Session cookie signing key |
| `db.py:820` | `DAILY_MESSAGE_LIMIT` | Per-user daily message cap (3) |
| `dashboard/templates/terms.html` / `privacy.html` | Legal text + **contact info** (GitHub/Discord/email) | Edit your ToS/Privacy directly |
| `dashboard/templates/base.html` | Footer links | The barely-visible ToS/Privacy links |

---

## 10. Things that are config-driven (no edits needed)

- **RNG roles + announcement channel** → `/settings rng_role` + `/settings rng_channel` (stored per guild in the DB)
- **Music/battle/suggestion channels** → `/settings` commands
- **Gambling lockout hours / max warns** → `/settings lockout_hours` / `/settings max_warns`

---

## 11. Database tables (`db.py` `SCHEMA`, lines 29–321)

All tables are created idempotently at startup (`CREATE TABLE IF NOT EXISTS`);
columns added later are handled by `_migrate()` (`db.py:387`), so existing
DBs upgrade in place.

| Table | Defined at | Purpose | Used by |
|---|---|---|---|
| `economy` | `db.py:29` | Gambling money, warns, lockout until, daily claim + streak — per (guild, user) | `cogs/gambling.py` |
| `predictions` | `db.py:40` | `/votebet` poll bets (amount, resolve date, multiplier, result) | `cogs/gambling.py` |
| `settings` | `db.py:58` | Per-guild config: channels (gambling/winners/suggestions/music/music battle/RNG), lockout hours, max warns, RNG tier roles | `cogs/settings.py` + everything reading `get_settings()` |
| `dashboard_users` | `db.py:72` | Dashboard login cache (username/avatar) + daily message counter | `dashboard/` |
| `message_logs` | `db.py:80` | Every dashboard message sent (admin moderation view) | `dashboard/routes.py` |
| `allowed_channels` | `db.py:88` | Dashboard send-access control: which roles/users may send to each channel | `dashboard/` |
| `dashboard_config` | `db.py:96` | Key/value store: sending kill-switch, GoonBot API key | `dashboard/` + `db.py` |
| `saved_messages` | `db.py:101` | `/message_add` + `/message_list` storage | `cogs/mensajes.py` |
| `music_songs` | `db.py:112` | The song collection: title/artist/url/platform/owner/ELO/lock | `cogs/music.py` |
| `music_battles` | `db.py:141` | Battles (normal / reclaim / SOTD): status, winner, channel+message refs | `cogs/music.py` |
| `music_votes` | `db.py:170` | Per-battle votes (`UNIQUE(battle_id, user_id)`) | `cogs/music.py` |
| `music_ownership` | `db.py:188` | Song ownership history (acquired/lost, claim battle) | `cogs/music.py` |
| `music_sotd` | `db.py:207` | Song of the Day — **dormant/unused** (SOTD is tracked via `music_battles` + `music_elo_history`) | — |
| `music_elo_history` | `db.py:226` | ELO change log for battles + SOTD (old→new, change, reason) | `cogs/music.py` |
| `music_cooldowns` | `db.py:245` | Battle/reclaim cooldown timestamps | `cogs/music.py` |
| `rng_users` | `db.py:257` | RNG profile per (guild, user): rolls, pity, GoonBot Tokens, equipped aura, last drop tier | `cogs/rng_engine.py` |
| `rng_item_registry` | `db.py:271` | Seeded item catalog (source: `RNG_ITEMS`, `db.py:328`) | `cogs/rng_engine.py` + `inventory_ui.py` |
| `rng_user_inventories` | `db.py:284` | Items owned per user (quantity, equipped flag) | `cogs/inventory_ui.py` |
| `rng_active_buffs` | `db.py:297` | Luck buffs: Luck Goon, Goon Charm (rolls_left), Goon Relic (permanent) | `cogs/rng_engine.py` |
| `rng_global_events` | `db.py:307` | Active luck-multiplier events (admin + scheduled) | `cogs/rng_engine.py` |
| `rng_last_use` | `db.py:314` | Daily-use gates (Re-Goon once/day) | `cogs/inventory_ui.py` |
| `rng_daily` | `db.py:325` | Daily login reward: last claim date + streak per (guild, user) | `cogs/gacha_ui.py` |
| `rng_missions` | `db.py:335` | Daily mission progress/claimed per (guild, user, date, mission) | `cogs/gacha_ui.py` + `rng_engine.py` |

---

## 12. Discord API & intents setup

| What | Where | Notes |
|---|---|---|
| Privileged intents | `main.py:24–25` | `members` (dashboard membership checks, member dropdowns) + `message_content` (music link auto-detect). **Presence is intentionally not requested.** |
| Developer Portal | — | In the Discord Developer Portal → Bot → Privileged Gateway Intents, enable **Server Members** and **Message Content** — the code requests them, but the portal must grant them or the bot disconnects. |
| Dashboard OAuth | `dashboard/auth.py:19–22` | `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` + scope `identify`. Redirect URL uses `DASHBOARD_BASE_URL` (`config.py:12`). |
| Command sync | `main.py` `setup_hook` | Commands sync to `GUILD_ID` (`config.py:4`); global commands are cleared so nothing shows up twice in the picker. |
| Dashboard membership check | `dashboard/app.py` (`check_membership`) | Uses the live bot + members intent instead of requesting the `guilds` OAuth scope. |
| Music link scanning | `main.py:25` | Needs Message Content intent enabled (see above) + `/settings music_channel`. |
| Required env vars | `config.py` / `.env` | `DISCORD_TOKEN`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `GUILD_ID`, `ADMIN_USER_ID`, `SESSION_SECRET` |

---

## 13. Command index (every `/command` → file:line)

### 🔧 Básicos (`main.py`)
| Command | Line |
|---|---|
| `/ping` | `main.py:214` |
| `/qtfn` | `main.py:223` |
| `/help` | `main.py:230` |
| `/redeploy` *(dev)* | `main.py:363` |

### 💬 Mensajes (`cogs/mensajes.py`)
| Command | Line |
|---|---|
| `/message_add` | `cogs/mensajes.py:49` |
| `/message_list` | `cogs/mensajes.py:57` |
| `/edit_message` | `cogs/mensajes.py:68` |

### 😂 Diversión (`cogs/fun.py`)
| Command | Line |
|---|---|
| `/roast` | `cogs/fun.py:13` |
| `/grape` | `cogs/fun.py:31` |
| `/rampage` | `cogs/fun.py:48` |

### 🎲 Gambling (`cogs/gambling.py`)
| Command | Line |
|---|---|
| `/roulette` | `cogs/gambling.py:341` |
| `/blackjack` | `cogs/gambling.py:450` |
| `/poker` | `cogs/gambling.py:538` |
| `/crash` | `cogs/gambling.py:590` |
| `/votebet create` | `cogs/gambling.py:676` (group `:132`) |
| `/votebet status` | `cogs/gambling.py:762` |
| `/gambling_warns` | `cogs/gambling.py:781` |
| `/gambling_pardon` *(admin)* | `cogs/gambling.py:805` |
| `/balance` | `cogs/gambling.py:820` |
| `/daily` | `cogs/gambling.py:830` |
| `/bet` | `cogs/gambling.py:861` |
| `/leaderboard` | `cogs/gambling.py:899` |

### 🎵 Música (`cogs/music.py`, group `:539`)
| Command | Line |
|---|---|
| `/music add` | `cogs/music.py:1108` |
| `/music list` | `cogs/music.py:1168` |
| `/music history` | `cogs/music.py:1198` |
| `/music info` | `cogs/music.py:1238` |
| `/music battle` | `cogs/music.py:1257` |
| `/music reclaim` | `cogs/music.py:1317` |

### 🔊 Soundboard (`cogs/soundboard.py`)
| Command | Line |
|---|---|
| `/play` | `cogs/soundboard.py:80` |
| `/sounds` | `cogs/soundboard.py:155` |

### 💡 Sugerencias (`cogs/suggestions.py`)
| Command | Line |
|---|---|
| `/suggest` | `cogs/suggestions.py:96` |

### 🎰 RNG Gacha (`cogs/rng_engine.py` + `cogs/inventory_ui.py` + `cogs/gacha_ui.py`)
| Command | Line |
|---|---|
| `/roll` | `cogs/rng_engine.py:669` — result + cooldown embeds carry the 🎲 Roll de nuevo / 🎲 ×10 buttons (`RollAgainView` at `:194`) |
| `/tokens` | `cogs/rng_engine.py:712` |
| `/shop list` | `cogs/rng_engine.py:778` (group `:145`) |
| `/shop buy` | `cogs/rng_engine.py:797` |
| `/rng event start` *(admin)* | `cogs/rng_engine.py:591` (groups `:146`, `:151`) |
| `/rng event stop` *(admin)* | `cogs/rng_engine.py:615` |
| `/rng event list` *(admin)* | `cogs/rng_engine.py:621` |
| `/inventory` | `cogs/inventory_ui.py:399` — includes bulk-sell dupes button |
| `/gacha daily` | `cogs/gacha_ui.py:465` (group `:282`) |
| `/gacha missions` | `cogs/gacha_ui.py:477` |
| `/gacha collection` | `cogs/gacha_ui.py:484` |
| `/gacha craft` | `cogs/gacha_ui.py:491` |
| `/gacha top` | `cogs/gacha_ui.py:498` |

### ⚙️ Settings (`cogs/settings.py`, group `:14`) — admin
| Command | Line |
|---|---|
| `/settings view` | `cogs/settings.py:20` |
| `/settings gambling_channel` | `cogs/settings.py:81` |
| `/settings suggestions_channel` | `cogs/settings.py:90` |
| `/settings winners_channel` | `cogs/settings.py:99` |
| `/settings lockout_hours` | `cogs/settings.py:108` |
| `/settings max_warns` | `cogs/settings.py:120` |
| `/settings music_channel` | `cogs/settings.py:132` |
| `/settings music_battle_channel` | `cogs/settings.py:142` |
| `/settings rng_channel` | `cogs/settings.py:152` |
| `/settings rng_role` | `cogs/settings.py:162` |

### 🔒 Dev / destructive (`cogs/admin.py`)
| Command | Line |
|---|---|
| `/los_horrores` *(dev, needs `NUKE_PASSWORD`)* | `cogs/admin.py:65` |

---

## Quick "where is X" index

| You want to change… | Go to |
|---|---|
| Drop odds of a tier | `config.py:104` |
| Add a new aura/item | `db.py:328` |
| Change an item's emoji/price | `db.py:328` |
| Token emoji | `config.py:31` |
| ELO steal % | `cogs/music.py:40` |
| SOTD boost range | `cogs/music.py:46` |
| Knockout cooldown days | `cogs/music.py:51` |
| Daily reward amount | `cogs/gambling.py:844` |
| Roulette payout | `cogs/gambling.py:400` |
| `/help` text | `main.py:230` |
| RNG recurring events | `config.py:126` |
| Daily mission targets/rewards | `config.py:66` |
| Crafting recipes | `config.py:78` |
| Combo / ×10 / daily balance | `config.py:46–62` |
| Dashboard message cap | `db.py:820` |
| ToS / Privacy text | `dashboard/templates/terms.html`, `privacy.html` |
