# 🧑‍💻 Goonbot 🤖

### Source code for my little discord bot project.
> If you want to try or know what features this bot has, feel free to contact me through GitHub or Discord!

---

![Goonbot's discord profile picture](https://cdn.discordapp.com/avatars/1440784584156385472/c77896c428794431a4288f5eb2f27021?size=256)

## What can this bot do? 👣

- [X] **Local AI Integration**: Talk to **AI** powered by local Ollama (`qwen2.5:0.5b`, dumbah...).
- [X] **Gambling & Economy**: Shared economy system (`/balance`, `/daily`, `/roulette`, `/blackjack`, `/poker`, `/crash`, `/bet`, `/leaderboard`, `/votebet`).
- [X] **Voice Soundboard**: Play custom sounds in voice channels (`/play`, `/sounds`).
- [X] **Web Dashboard**: Web control panel with Discord OAuth2 to manage bot messages and settings.
- [X] **Fun Commands**: Roast users, rampage reactions, and secret admin commands.

---

## 🔐 Discord Developer Portal — required intents

The bot uses slash commands (`/`) only, so it does **not** need the Message
Content intent. The only privileged intent you must enable is **Server Members**.

### Required

| Intent | Privileged | Why it's needed |
| --- | --- | --- |
| **Server Members Intent** | ✅ Yes | The web dashboard checks guild membership and resolves member names. |


### Intentionally disabled

| Intent | Why it's not needed |
| --- | --- |
| Message Content Intent | All commands are slash commands, which don't read message text. |
| Presence Intent | The bot doesn't read user status/activity. |

---

### Links & Contact
- **GitHub Repos**: [ttsimonerd Repositories](https://github.com/ttsimonerd?tab=repositories)
- **Discord Profile**: [el_navajas](https://discord.com/users/988470489909432334)
