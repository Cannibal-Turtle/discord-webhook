#!/usr/bin/env python3
import os
import requests
import sys

BOT_TOKEN  = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
if not BOT_TOKEN or not CHANNEL_ID:
    sys.exit("ERROR: DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID must be set")

# build your fake completion message
message = (
    "<@&1329391480435114005> | <@&1329391480435114005>\n"
    "## ꧁ᐟᐟ ◌ೄ⟢  Completion Announcement  :blueberries: ˚. ᵎᵎ˖ˎˊ-\n"
    "◈· ─ · ─ · ─ · ❁ · ─ ·𖥸· ─ · ❁ · ─ · ─ · ─ ·◈\n"
    "***『[Test Novel](https://example.com)』— officially completed!*** :turtle_super_hyper:\n\n"
    "*The last chapter, [Chapter 42](https://example.com/ch42), has now been released.*\n"
    "*After 2 months of updates, Test Novel is now fully translated with 42 chapters!*\n"
    "✎﹏﹏﹏﹏﹏﹏﹏﹏\n"
    "-# Check out other translated projects at https://discord.com/channels/... and react to get the latest updates~"
)

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
print("✅ Test completion sent successfully")
