import os
import json
import asyncio
from datetime import datetime
import aiohttp
from discord.ext import commands, tasks
import discord

# ---------------------------------------------------------------
# ClickUp Logger Cog
# Captures Discord server activity and syncs it to a ClickUp Doc
# for Gossip Gabi to read and summarize.
#
# Required env vars:
#   CLICKUP_API_TOKEN    - Your ClickUp Personal API Token
#   CLICKUP_WORKSPACE_ID - Your workspace ID (numeric)
#   CLICKUP_DOC_ID       - The doc ID (from the doc URL)
#   CLICKUP_PAGE_ID      - The page ID within the doc
# ---------------------------------------------------------------

EVENT_LOG_FILE = "event_log.json"


def load_event_log():
    if not os.path.exists(EVENT_LOG_FILE):
        return []
    try:
        with open(EVENT_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_event_log(events):
    with open(EVENT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def clear_event_log():
    save_event_log([])


class ClickUpLogger(commands.Cog, name="ClickUpLogger"):
    """Logs Discord server activity to a ClickUp Doc."""

    def __init__(self, bot):
        self.bot = bot
        self.event_buffer = []
        self.clickup_token = os.getenv("CLICKUP_API_TOKEN")
        self.workspace_id = os.getenv("CLICKUP_WORKSPACE_ID")
        self.doc_id = os.getenv("CLICKUP_DOC_ID")
        self.page_id = os.getenv("CLICKUP_PAGE_ID")
        self.sync_to_clickup.start()
        self.save_buffer_locally.start()

    def cog_unload(self):
        self.sync_to_clickup.cancel()
        self.save_buffer_locally.cancel()

    def _format_event(self, event_type, **kwargs):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details = " | ".join(f"{k}: {v}" for k, v in kwargs.items())
        return {
            "timestamp": timestamp,
            "type": event_type,
            "details": details,
            "raw": kwargs
        }

    # ---------------------------------------------------------------
    # Event Listeners
    # ---------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        self.event_buffer.append(self._format_event(
            "MESSAGE",
            author=f"{message.author.display_name} ({message.author.name})",
            channel=f"#{message.channel.name}",
            content=message.content[:300] if message.content else "(media/empty)"
        ))

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.author or message.author.bot:
            return
        self.event_buffer.append(self._format_event(
            "DELETED MESSAGE",
            author=f"{message.author.display_name} ({message.author.name})",
            channel=f"#{message.channel.name}",
            content=message.content[:300] if message.content else "(unknown)"
        ))

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot:
            return
        if before.content == after.content:
            return
        self.event_buffer.append(self._format_event(
            "EDITED MESSAGE",
            author=f"{before.author.display_name} ({before.author.name})",
            channel=f"#{before.channel.name}",
            before=before.content[:150] if before.content else "(empty)",
            after=after.content[:150] if after.content else "(empty)"
        ))

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        self.event_buffer.append(self._format_event(
            "MEMBER BANNED",
            user=f"{user.display_name} ({user.name})"
        ))

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        self.event_buffer.append(self._format_event(
            "MEMBER UNBANNED",
            user=f"{user.display_name} ({user.name})"
        ))

    @commands.Cog.listener()
    async def on_member_join(self, member):
        self.event_buffer.append(self._format_event(
            "MEMBER JOINED",
            user=f"{member.display_name} ({member.name})"
        ))

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        self.event_buffer.append(self._format_event(
            "MEMBER LEFT",
            user=f"{member.display_name} ({member.name})"
        ))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        if before.channel != after.channel:
            if after.channel and not before.channel:
                self.event_buffer.append(self._format_event(
                    "VOICE JOIN",
                    user=member.display_name,
                    channel=f"#{after.channel.name}"
                ))
            elif before.channel and not after.channel:
                self.event_buffer.append(self._format_event(
                    "VOICE LEAVE",
                    user=member.display_name,
                    channel=f"#{before.channel.name}"
                ))
            else:
                self.event_buffer.append(self._format_event(
                    "VOICE MOVE",
                    user=member.display_name,
                    from_channel=f"#{before.channel.name}",
                    to_channel=f"#{after.channel.name}"
                ))

    # ---------------------------------------------------------------
    # Background Tasks
    # ---------------------------------------------------------------

    @tasks.loop(minutes=5)
    async def save_buffer_locally(self):
        """Save buffer to local file every 5 minutes as backup."""
        if not self.event_buffer:
            return
        count = len(self.event_buffer)
        existing = load_event_log()
        existing.extend(self.event_buffer)
        save_event_log(existing)
        self.event_buffer.clear()
        print(f"[ClickUp Logger] Saved {count} events to local file.")

    @save_buffer_locally.before_loop
    async def before_save(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=60)
    async def sync_to_clickup(self):
        """Sync local event log to ClickUp Doc every hour."""
        events = load_event_log()
        if not events:
            return

        if not all([self.clickup_token, self.workspace_id, self.doc_id, self.page_id]):
            print("[ClickUp Logger] Missing env vars, skipping sync.")
            return

        # Format events as markdown for the doc
        lines = []
        for event in events:
            emoji = {
                "MESSAGE": "💬",
                "DELETED MESSAGE": "🗑️",
                "EDITED MESSAGE": "✏️",
                "MEMBER BANNED": "🔨",
                "MEMBER UNBANNED": "✅",
                "MEMBER JOINED": "📥",
                "MEMBER LEFT": "📤",
                "VOICE JOIN": "🎙️",
                "VOICE LEAVE": "🔇",
                "VOICE MOVE": "🔀"
            }.get(event["type"], "📌")
            lines.append(f"{emoji} [{event['timestamp']}] **{event['type']}** | {event['details']}")

        markdown_content = "\n\n".join(lines)

        try:
            url = f"https://api.clickup.com/api/v3/workspaces/{self.workspace_id}/docs/{self.doc_id}/pages/{self.page_id}"
            headers = {
                "Authorization": self.clickup_token,
                "Content-Type": "application/json"
            }

            async with aiohttp.ClientSession() as session:
                # Try to get existing content first
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        existing = data.get("content", "")
                    else:
                        existing = ""

                # Append new events
                separator = "\n\n---\n\n"
                if existing and existing.strip():
                    updated = existing + separator + markdown_content
                else:
                    updated = markdown_content

                payload = {
                    "content": updated,
                    "content_format": "text/md"
                }

                async with session.put(url, headers=headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        clear_event_log()
                        print(f"[ClickUp Logger] Synced {len(events)} events to ClickUp Doc.")
                    else:
                        error_text = await resp.text()
                        print(f"[ClickUp Logger] Sync failed ({resp.status}): {error_text}")
                        print("[ClickUp Logger] Events preserved in local file.")

        except Exception as e:
            print(f"[ClickUp Logger] Sync error: {e}")
            print("[ClickUp Logger] Events preserved in local file.")

    @sync_to_clickup.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(30)  # Wait a bit after boot before first sync


async def setup(bot):
    await bot.add_cog(ClickUpLogger(bot))
