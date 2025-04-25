#!/usr/bin/env python3
import os
import asyncio
import aiohttp
from dateutil import parser as dateparser

# ─── CONFIG ───────────────────────────────────────────
TOKEN      = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.getenv("DISCORD_COMMENTS_CHANNEL")
if not TOKEN or not CHANNEL_ID:
    raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_COMMENTS_CHANNEL must be set")
API_URL    = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
# ───────────────────────────────────────────────────────

async def demo_comment_alert():
    async with aiohttp.ClientSession() as session:
        # ─── build the message content ─────────────────────
        role_id     = "<@&1329391480435114005>"
        message_txt = (
            f"<:happy_turtle_ping:1365253831361036368> "
            f"New comment for **Demo Novel** || {role_id}"
        )

        # ─── build an embed like your real script does ─────
        author      = "DemoUser"
        chapter     = "Chapter 5"
        comment_txt = "This is a demo comment — it might get truncated if too long."
        reply_chain = "In reply to: “I love this part!”"
        host        = "DemoHost"
        host_logo   = "https://example.com/logo.png"
        link        = "https://example.com/democomment"
        # wrap comment in ❛❛…❜❜ and truncate at 200 chars for demo
        safe = comment_txt
        if len(safe) > 200:
            safe = safe[:200].rstrip() + "..."
        title = f"❛❛{safe}❜❜"
        timestamp = dateparser.parse("2025-04-25T12:00:00+00:00").isoformat()

        embed = {
            "author": {
                "name": f"comment by {author} 🕊️ {chapter}",
                "url":  link
            },
            "title":     title,
            "description": reply_chain,
            "timestamp": timestamp,
            "color":     int("F0C7A4", 16),
            "footer": {
                "text":     host,
                "icon_url": host_logo
            }
        }

        payload = {
            "content": message_txt,
            "embeds":  [embed]
        }

        # ─── send it ────────────────────────────────────────
        headers = {
            "Authorization": f"Bot {TOKEN}",
            "Content-Type":  "application/json"
        }
        async with session.post(API_URL, headers=headers, json=payload) as resp:
            if resp.status in (200, 204):
                print("✅ Demo comment alert sent")
            else:
                text = await resp.text()
                print(f"❌ Failed ({resp.status}): {text}")

if __name__ == "__main__":
    asyncio.run(demo_comment_alert())
