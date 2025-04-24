import os
import json
import asyncio
import feedparser
from dateutil import parser as dateparser
import aiohttp

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN       = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID  = os.environ["DISCORD_COMMENTS_CHANNEL"]
STATE_FILE  = "state_rss.json"
FEED_KEY    = "comments_last_guid"
RSS_URL     = "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/comments.py"
API_URL     = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
# ────────────────────────────────────────────────────────────────────────────────

def load_state():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        initial = {
          "free_last_guid":    None,
          "paid_last_guid":    None,
          "comments_last_guid": None
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(initial, f, indent=2, ensure_ascii=False)
        return initial

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

async def main():
    state   = load_state()
    feed    = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest
    guids   = [(e.get("guid") or e.get("id")) for e in entries]
    last     = state.get(FEED_KEY)
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
            start_marker = "❛❛"
            end_marker   = "❜❜"
            ellipsis     = "..."
            # compute how many chars of comment_txt we can keep
            # total max = 256, minus markers and ellipsis
            content_max = 256 - len(start_marker) - len(end_marker) - len(ellipsis)
            # if too long, truncate and add "..."
            if len(comment_txt) > content_max:
                truncated = comment_txt[:content_max].rstrip()
                safe_comment = truncated + ellipsis
            else:
                safe_comment = comment_txt
            full_title = f"{start_marker}{safe_comment}{end_marker}"

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
        if new_last and new_last != last:
            state[FEED_KEY] = new_last
            save_state(state)
            print(f"💾 Updated {STATE_FILE} → {new_last}")

if __name__ == "__main__":
    asyncio.run(main())
