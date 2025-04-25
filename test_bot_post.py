#!/usr/bin/env python3
import os
import requests
import sys

# ─── CONFIG ───────────────────────────────────────────
DISCORD_BOT_TOKEN  = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
if not DISCORD_BOT_TOKEN or not DISCORD_CHANNEL_ID:
    sys.exit("ERROR: DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID must be set")

# ─── DUMMY VALUES ─────────────────────────────────────
base_mention = "<@&1329391480435114005>"
ONGOING_ROLE = "<@&1329502951764525187>"
disp_label   = "EXTRAS + SIDE STORIES"
remaining    = (
    "***[《Test Novel》](https://example.com/novel)*** is almost at the very end — "
    "just 2 extras and 1 side story left before we wrap up this journey for good "
    "<:turtle_cowboy2:1365266375274266695>."
)
cm           = "New extras and side stories just dropped"
host         = "ExampleHost"

# ─── BUILD MESSAGE ────────────────────────────────────
msg = (
    f"{base_mention} | {ONGOING_ROLE}\n"
    f"## :lotus:･ﾟ✧ NEW {disp_label} JUST DROPPED ✧ﾟ･:lotus:\n"
    f"{remaining}\n"
    f"{cm} in {host}'s advance access today. "
    "Thanks for sticking with this one ‘til the end. It means a lot. "
    "Please show your final love and support by leaving comments on the site~ "
    "<:turtlelovefamily:1365266991690285156>"
)

# ─── SEND VIA BOT ────────────────────────────────────
url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
headers = {
    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
    "Content-Type":  "application/json"
}
payload = {
    "content": msg,
    "allowed_mentions": { "parse": ["roles"] },
    "flags": 4
}

resp = requests.post(url, headers=headers, json=payload)
resp.raise_for_status()
print("✅ Test extras alert sent successfully")
