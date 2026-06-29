import os
import json
import asyncio
import feedparser
from dateutil import parser as dateparser
import aiohttp
from message_context import build_feed_context, entry_get
from message_renderer import render_message, to_discord_api_payload
from guid_state import entry_guid_identity, format_seen_guid, raw_guid_from_entry, seen_guid_identities

# ─── CONFIG ────────────────────────────────────────────────────────────────────
from config_loader import (
    server_channel_id_str,
    get_novel_role_id,
    require_feed_value,
    require_feeds_value,
    require_feed_url,
    require_file_value,
    require_server_value,
    role_id_to_mention,
)

TOKEN      = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = server_channel_id_str("comments")

STATE_FILE = require_file_value("rss_state_path")
FEED_KEY   = require_feed_value("comments", "last_guid_key")
RSS_URL    = require_feed_url("comments")
API_URL    = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"

SEEN_KEY       = require_feed_value("comments", "seen_key")
LAST_POST_TIME = require_feed_value("comments", "last_post_time_key")
SEEN_CAP       = int(require_feeds_value("seen_cap"))
TIME_BACKSTOP  = bool(require_feeds_value("time_backstop"))
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
    return format_seen_guid(entry, default_host="")

def parse_pub_iso(entry):
    pubdate_raw = getattr(entry, "published", None)
    if not pubdate_raw:
        return None
    try:
        return dateparser.parse(pubdate_raw)
    except Exception:
        return None


def setting_bool(env_name: str, server_key: str, default: bool = True) -> bool:
    raw = os.getenv(env_name)

    if raw is None:
        try:
            raw = require_server_value(server_key)
        except RuntimeError:
            return default

    if isinstance(raw, bool):
        return raw

    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

def include_novel_updates_comments() -> bool:
    return setting_bool(
        "INCLUDE_NOVEL_UPDATES_COMMENTS",
        "include_novel_updates_comments",
        True,
    )

def is_novel_updates_host(host: str) -> bool:
    key = " ".join(str(host or "").strip().casefold().split())
    compact = key.replace(" ", "").replace(".", "")
    return key == "novel updates" or compact in {
        "novelupdates",
        "novelupdatescom",
        "novelupdate",
    }

def is_novel_updates_entry(entry) -> bool:
    return is_novel_updates_host(entry_get(entry, "host", default=""))

def get_series_role(entry) -> str:
    short_code = (entry.get("short_code") or "").strip().upper()
    role_id = get_novel_role_id(short_code)
    return role_id_to_mention(role_id) if role_id else ""

def build_comment_title(comment_txt: str, comment_image: str = "") -> str:
    start_marker = "❛❛"
    end_marker = "❜❜"
    ellipsis = "..."

    content_max = 256 - len(start_marker) - len(end_marker) - len(ellipsis)

    if len(comment_txt) > content_max:
        safe_comment = comment_txt[:content_max].rstrip() + ellipsis
    else:
        safe_comment = comment_txt

    if comment_image and comment_txt == "Sticker comment":
        return ""

    return f"{start_marker}{safe_comment}{end_marker}"

async def main():
    state   = load_state()
    feed    = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest (keep your order)
    seen = seen_guid_identities(state.get(SEEN_KEY, []))

    # optional time backstop
    last_post_time = state.get(LAST_POST_TIME)
    last_post_dt = dateparser.parse(last_post_time) if (TIME_BACKSTOP and last_post_time) else None

    include_nu_comments = include_novel_updates_comments()
    skipped_nu_comments = 0

    to_send = []
    for e in entries:
        guid_key = entry_guid_identity(e)
        if not guid_key:
            continue

        if guid_key in seen:
            continue
        if last_post_dt is not None:
            dt = parse_pub_iso(e)
            # if we can parse pubdate and it isn't newer than last posted time, skip
            if dt and dt < last_post_dt:
                continue
        if not include_nu_comments and is_novel_updates_entry(e):
            norm = normalize_guid(e)
            state[SEEN_KEY].append(norm)
            seen.add(guid_key)
            skipped_nu_comments += 1
            continue
        to_send.append(e)

    if skipped_nu_comments:
        save_state(state)
        print(
            f"🚫 Skipped {skipped_nu_comments} Novel Updates comment(s) "
            "because include_novel_updates_comments is false."
        )

    last = state.get(FEED_KEY)
    
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
            
            ctx = build_feed_context(entry)
            
            role_mention = get_series_role(entry)
            role_tail = f" {role_mention}" if role_mention else ""
            
            comment_txt = ctx["description"]
            comment_image = ctx["comment_image_url"]
            
            color_key = (
                "novel_updates_comments"
                if ctx["host"].strip().lower() == "novel updates"
                else "comments"
            )
            
            ctx.update({
                "comment_title": build_comment_title(comment_txt, comment_image),
                "comment_color_key": color_key,
                "comment_role_tail": role_tail,
            })
            
            payload = to_discord_api_payload(render_message("comments", ctx))

            async with session.post(API_URL, headers=headers, json=payload) as resp:
                text = await resp.text()
                if resp.status in (200, 204):
                    print(f"✅ Sent comment {guid}")
                    norm = normalize_guid(entry)
                    state[SEEN_KEY].append(norm)
                    seen.add(entry_guid_identity(entry))
                    state[LAST_POST_TIME] = (parse_pub_iso(entry) or dateparser.parse("1970-01-01")).isoformat()
                    new_last = raw_guid_from_entry(entry)
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
