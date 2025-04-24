import os
import json
import asyncio
import feedparser
from dateutil import parser as dateparser
import aiohttp

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN       = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID  = os.environ["DISCORD_COMMENTS_CHANNEL"]
STATE_FILE  = "state_comments.json"
RSS_URL     = "https://cannibal-turtle.github.io/rss-feed/aggregated_comments_feed.xml"
API_URL     = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
# ────────────────────────────────────────────────────────────────────────────────

def load_state():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        init = {"last_guid": None}
        json.dump(init, open(STATE_FILE, "w", encoding="utf-8"), indent=2)
        return init

def save_state(state):
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), indent=2)

async def main():
    state   = load_state()
    feed    = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest
    guids   = [(e.get("guid") or e.get("id")) for e in entries]
    last    = state.get("last_guid")
    to_send = entries[guids.index(last)+1:] if last in guids else entries

    if not to_send:
        print("🛑 No new comments to send.")
        return

    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type":  "application/json",
    }

    async with aiohttp.ClientSession() as session:
        new_last = last

        for entry in to_send:
            guid        = entry.get("guid") or entry.get("id")
            title       = entry.get("title", "").strip()
            role_id     = entry.get("discord_role_id", "").strip()
            author      = entry.get("author") or entry.get("dc_creator", "")
            chapter     = entry.get("chapter", "").strip()
            comment_txt = entry.get("description", "").strip()
            reply_chain = entry.get("reply_chain", "").strip()
            host        = entry.get("host", "").strip()
            host_logo   = (entry.get("hostLogo") or entry.get("hostlogo") or {}).get("url", "")
            link        = entry.get("link", "").strip()
            pubdate_raw = getattr(entry, "published", None)
            timestamp   = dateparser.parse(pubdate_raw).isoformat() if pubdate_raw else None

            # ─── Truncate the quoted comment so title <= 256 chars ──────────
            full_title = f"❛❛{comment_txt}❜❜"
            if len(full_title) > 256:
                # leave room for the closing quotes
                truncated = full_title[:254]  # 254 + "❜❜" = 256
                full_title = truncated.rstrip("❜") + "❜❜"

            # ─── Build the embed dict (no author icon_url) ────────────────
            embed = {
                "author": {
                    "name": f"comment by {author} 🕊️ {chapter}",
                    "url":  link
                },
                "title":     full_title,
                "timestamp": timestamp,
                "color":     int("F0C7A4", 16),
                "footer": {
                    "text":     host,
                    "icon_url": host_logo
                }
            }
            # only include description if reply_chain exists
            if reply_chain:
                embed["description"] = reply_chain

            payload = {
                "content": f"New comment for **{title}** || {role_id}",
                "embeds":  [embed]
            }

            async with session.post(API_URL, headers=headers, json=payload) as resp:
                text = await resp.text()
                if resp.status in (200, 204):
                    print(f"✅ Sent comment {guid}")
                    new_last = guid
                else:
                    print(f"❌ Error {resp.status} for {guid}: {text}")

        # ─── Save the new last_guid once ───────────────────────────────
        if new_last != last:
            state["last_guid"] = new_last
            save_state(state)
            print(f"💾 Updated state_comments.json → {new_last}")

if __name__ == "__main__":
    asyncio.run(main())
