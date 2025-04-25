#!/usr/bin/env python3
import os
import requests
import sys

# ─── CONFIG ───────────────────────────────────────────
DISCORD_BOT_TOKEN  = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
if not DISCORD_BOT_TOKEN or not DISCORD_CHANNEL_ID:
    sys.exit("ERROR: DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID must be set")

# these would normally come from your mapping + parser
base_mention  = "<@&1329391480435114005>"
ONGOING_ROLE  = "<@&1329502951764525187>"
world_number  = 3
unlocked_md   = "World 3 ⋆ Chapter 10, Chapter 11"
locked_md     = "World 3 ⋆ Chapter 12, Chapter 13"
novel = {
    "novel_title":     "Example Novel",
    "novel_link":      "https://example.com/novel",
    "host":            "ExampleHost",
    "custom_emoji":    "🦋",
    "discord_role_url":"https://discord.com/channels/123456789/987654321"
}

# ─── BUILD MESSAGE ────────────────────────────────────
message = (
    f"{base_mention} | {ONGOING_ROLE}\n"
    "## 🔊 NEW ARC ALERT˚ · .˚ ༘🦋⋆｡˚\n"
    f"<a:Turtle_Police:1365223650466205738>***《World {world_number}》is Live for***\n"
    f"### [{novel['novel_title']}]({novel['novel_link']}) <:Hehe:1329429547229122580>\n"
    "❀° ┄───────────────────────╮\n"
    "**`Unlocked 🔓`**\n"
    f"||{unlocked_md}||\n\n"
    "**`Locked 🔐`**\n"
    f"||{locked_md}||\n"
    "╰───────────────────────┄ °❀\n"
    f"> *Advance access is ready for you on {novel['host']}! 🌹*\n"
    "✎﹏﹏﹏﹏﹏﹏﹏﹏\n"
    f"-# React to the {novel['custom_emoji']} @ {novel['discord_role_url']} to get notified on updates and announcements~"
)

# ─── SEND VIA BOT ────────────────────────────────────
url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
headers = {
    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
    "Content-Type":  "application/json"
}
payload = {
    "content": message,
    "allowed_mentions": {"parse": ["roles"]},
    "flags": 4
}

resp = requests.post(url, headers=headers, json=payload)
resp.raise_for_status()
print("✅ Test ARC alert sent successfully")
