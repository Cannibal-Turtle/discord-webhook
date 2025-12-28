import os
import json
import asyncio
import feedparser
from dateutil import parser as dateparser
import aiohttp
import html
from urllib.parse import urlsplit, urlunsplit

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN       = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID  = os.environ["DISCORD_COMMENTS_CHANNEL"]
STATE_FILE  = "state_rss.json"
FEED_KEY    = "comments_last_guid"
RSS_URL     = "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/aggregated_comments_feed.xml"
API_URL     = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
SEEN_KEY       = "seen_guids"       # bounded history of posted items
LAST_POST_TIME = "last_post_time"   # ISO string of last successful post time
SEEN_CAP       = 500                # keep the last 500 GUIDs
TIME_BACKSTOP  = True               # also require pubDate > last_post_time
# ────────────────────────────────────────────────────────────────────────────────

def load_state():
    try:
        st = json.load(open(STATE_FILE, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        st = {
          "free_last_guid":     None,
          "paid_last_guid":     None,
          "comments_last_guid": None,
          SEEN_KEY:             [],
          LAST_POST_TIME:       None,
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2, ensure_ascii=False)
        return st

    # migrate if missing
    changed = False
    if SEEN_KEY not in st:
        st[SEEN_KEY] = []
        changed = True
    if LAST_POST_TIME not in st:
        st[LAST_POST_TIME] = None
        changed = True
    if changed:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2, ensure_ascii=False)
    return st

def save_state(state):
    # cap the seen list
    if isinstance(state.get(SEEN_KEY), list) and len(state[SEEN_KEY]) > SEEN_CAP:
        state[SEEN_KEY] = state[SEEN_KEY][-SEEN_CAP:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def normalize_guid(entry):
    """
    Composite identity so tiny encoding changes or cross-host collisions don't dup.
    host::guid (guid unescaped, URL host lowercased if URL-like)
    """
    host = (entry.get("host") or "").strip().lower()
    raw  = (entry.get("guid") or entry.get("id") or "").strip()
    raw  = html.unescape(raw)
    # normalize URL-ish GUIDs
    try:
        p = urlsplit(raw)
        if p.scheme and p.netloc:
            raw = urlunsplit((p.scheme, p.netloc.lower(), p.path, p.query, p.fragment))
    except Exception:
        pass
    return f"{host}::{raw}"

def parse_pub_iso(entry):
    pubdate_raw = getattr(entry, "published", None)
    if not pubdate_raw:
        return None
    try:
        return dateparser.parse(pubdate_raw)
    except Exception:
        return None

async def main():
    state   = load_state()
    feed    = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest (keep your order)
    seen = set(state.get(SEEN_KEY, []))

    # optional time backstop
    last_post_time = state.get(LAST_POST_TIME)
    last_post_dt = dateparser.parse(last_post_time) if (TIME_BACKSTOP and last_post_time) else None

    to_send = []
    for e in entries:
        norm = normalize_guid(e)
        if norm in seen:
            continue
        if last_post_dt is not None:
            dt = parse_pub_iso(e)
            # if we can parse pubdate and it isn't newer than last posted time, skip
            if dt and dt <= last_post_dt:
                continue
        to_send.append(e)

    last = state.get(FEED_KEY)  # keep your legacy key around (harmless)

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
            role_id     = ""
            if "discord_role_id" in entry:
                role_id = entry["discord_role_id"].get("value", "").strip()
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

            # pick embed color per host
            default_hex = "F0C7A4"
            nu_hex = "2d3f51"
            color_hex = nu_hex if host.strip().lower() == "novel updates" else default_hex
            
            # ─── Build the embed dict (no author icon_url) ────────────────
            embed = {
                "author": {
                    "name": f"comment by {author} 🕊️ {chapter}",
                    "url":  link
                },
                "title":     full_title,
                "timestamp": timestamp,
                "color":     int(color_hex, 16),  # <-- special color for Novel Updates
                "footer": {
                    "text":     host,
                    "icon_url": host_logo
                }
            }

            # only include description if reply_chain exists
            if reply_chain:
                embed["description"] = reply_chain

            payload = {
                "content": f"<a:7977heartslike:1368146209981857792> New comment for **{title}** || {role_id} <a:flowersandpetals:1444260426182295623>",
                "embeds":  [embed]
            }

            async with session.post(API_URL, headers=headers, json=payload) as resp:
                text = await resp.text()
                if resp.status in (200, 204):
                    print(f"✅ Sent comment {guid}")
                    norm = normalize_guid(entry)
                    state[SEEN_KEY].append(norm)
                    state[LAST_POST_TIME] = (parse_pub_iso(entry) or dateparser.parse("1970-01-01")).isoformat()
                    new_last = guid
                    save_state(state)
                else:
                    print(f"❌ Error {resp.status} for {guid}: {text}")

        # ─── Save the new last_guid once ───────────────────────────────
        if new_last and new_last != last:
            state[FEED_KEY] = new_last
            save_state(state)
            print(f"💾 Updated {STATE_FILE} → {new_last}")

if __name__ == "__main__":
    asyncio.run(main())
