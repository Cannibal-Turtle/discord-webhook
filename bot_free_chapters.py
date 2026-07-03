import os
import json
import asyncio
import feedparser
import re
from datetime import datetime, timezone
from dateutil import parser as dateparser
import html
from urllib.parse import urlsplit, urlunsplit

import discord
import requests

from message_context import build_feed_context
from message_renderer import render_message, to_discord_py_kwargs
from guid_state import entry_guid_identity, format_seen_guid, raw_guid_from_entry, seen_guid_identities
from git_state_commit import commit_state_update

from novel_mappings import get_translator_url

try:
    from status_update_dispatcher import trigger_status_update
except Exception as import_exc:
    _STATUS_UPDATE_IMPORT_ERROR = str(import_exc)

    def trigger_status_update(title: str, host: str) -> bool:
        print(
            f"⚠️ Optional card status update unavailable; skipped {title}: "
            f"{_STATUS_UPDATE_IMPORT_ERROR}"
        )
        return False

# ─── CONFIG ────────────────────────────────────────────────────────────────────
from config_loader import (
    server_channel_id,
    get_novel_role_id,
    require_feed_value,
    require_feeds_value,
    require_feed_url,
    require_file_value,
    require_role_value,
    require_server_value,
    server_value,
    role_id_to_mention,
)

TOKEN      = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = server_channel_id("free_chapters")

STATE_FILE = require_file_value("rss_state_path")
STATE_CHANGED = False
FEED_KEY   = require_feed_value("free", "last_guid_key")
RSS_URL    = require_feed_url("free")

SEEN_KEY       = require_feed_value("free", "seen_key")
LAST_POST_TIME = require_feed_value("free", "last_post_time_key")
SEEN_CAP       = int(require_feeds_value("seen_cap"))
TIME_BACKSTOP  = bool(require_feeds_value("time_backstop"))

GLOBAL_MENTION = role_id_to_mention(require_role_value("free_global"))
NSFW_ROLE      = role_id_to_mention(require_role_value("nsfw"))

TRANSLATOR_URL = str(server_value("translator_url", "") or "").strip()
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
        save_state(st)
        return st

    changed = False
    if SEEN_KEY not in st:
        st[SEEN_KEY] = []
        changed = True
    if LAST_POST_TIME not in st:
        st[LAST_POST_TIME] = None
        changed = True
    if changed:
        save_state(st)
    return st

def save_state(state):
    global STATE_CHANGED
    if isinstance(state.get(SEEN_KEY), list) and len(state[SEEN_KEY]) > SEEN_CAP:
        state[SEEN_KEY] = state[SEEN_KEY][-SEEN_CAP:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    STATE_CHANGED = True


def commit_state_if_changed():
    if STATE_CHANGED:
        commit_state_update(STATE_FILE)

def is_nsfw(entry) -> bool:
    cat = (entry.get("category") or "").strip().upper()
    return cat == "NSFW"

def get_series_role(entry) -> str:
    short_code = (entry.get("short_code") or "").strip().upper()
    role_id = get_novel_role_id(short_code)
    return role_id_to_mention(role_id)

def _join_role_mentions(*parts) -> str:
    """Join pieces with ' | ', split/trim on pipes/spaces, and dedupe in order."""
    seen, out = set(), []
    for p in parts:
        if not p:
            continue
        for seg in (x.strip() for x in re.split(r"[| ]+", p) if x.strip()):
            if seg not in seen:
                seen.add(seg)
                out.append(seg)
    return " | ".join(out)

def _build_chapter_mention(series_role: str, nsfw: bool, global_mention: str) -> str:
    """
    Compose: <series role> [| <NSFW_ROLE>] | <GLOBAL_MENTION>
    If series_role is empty, you’ll just get: <GLOBAL_MENTION>.
    """
    nsfw_tail = NSFW_ROLE if nsfw else None
    return _join_role_mentions(series_role, nsfw_tail, global_mention)

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

def first_chapter_release_enabled() -> bool:
    return setting_bool(
        "ANNOUNCE_FIRST_CHAPTER_RELEASE",
        "announce_first_chapter_release",
        True,
    )

def _clean_compare(s: str) -> str:
    s = (s or "").replace("\u00A0", " ").strip().lower()
    return re.sub(r"\s+", " ", s)

def is_probable_first_free_chapter(entry) -> bool:
    raw_chap = entry.get("chapter") or ""
    raw_extend = entry.get("chaptername") or ""

    fields = [_clean_compare(raw_chap), _clean_compare(raw_extend)]
    text = " ".join(x for x in fields if x)

    if not text:
        return False

    if "prologue" in text:
        return True

    if re.search(r"\bch(?:apter)?\.?\s*0*1\b", text):
        return True

    if re.search(r"\bep(?:isode)?\.?\s*0*1\b", text):
        return True

    if re.search(r"(?:^|\s)1[．\.]\s*0*1\b", text):
        return True

    for field in fields:
        if re.fullmatch(r"0*1", field):
            return True

    return False

def should_hold_first_free_chapter(entry) -> bool:
    if first_chapter_release_enabled():
        return False

    return is_probable_first_free_chapter(entry)

def normalize_guid(entry):
    return format_seen_guid(entry, default_host='')

def parse_pub_iso(entry):
    pub_raw = getattr(entry, "published", None)
    if not pub_raw:
        return None
    try:
        return dateparser.parse(pub_raw)
    except Exception:
        return None

async def send_new_entries():
    state = load_state()
    last  = state.get(FEED_KEY)
    feed  = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest

    seen = seen_guid_identities(state.get(SEEN_KEY, []))
    last_post_time = state.get(LAST_POST_TIME)
    last_post_dt = dateparser.parse(last_post_time) if (TIME_BACKSTOP and last_post_time) else None

    to_send = []
    for e in entries:
        guid_key = entry_guid_identity(e)
        if not guid_key:
            continue

        if guid_key in seen:
            continue
        if last_post_dt is not None:
            dt = parse_pub_iso(e)
            if dt and dt < last_post_dt:
                continue
        to_send.append(e)

    if not to_send:
        print("🛑 No new free chapters—skipping Discord login.")
        return

    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        channel = bot.get_channel(CHANNEL_ID)
        if channel is None:
            print(f"❌ Cannot find channel {CHANNEL_ID}")
            await bot.close()
            return

        updated_titles = set()  # (title, host)

        new_last = last

        for entry in to_send:
            guid = entry.get("guid") or entry.get("id")
            guid_key = entry_guid_identity(entry)

            # Pull source fields first
            host        = (entry.get("host") or "").strip()
            series_role = get_series_role(entry)
            nsfw_flag   = is_nsfw(entry)

            # Build mention line *before* content
            mention_line = _build_chapter_mention(
                series_role=series_role,
                nsfw=nsfw_flag,
                global_mention=GLOBAL_MENTION,
            )

            ctx = build_feed_context(entry)

            if should_hold_first_free_chapter(entry):
                print(
                    f"⏳ Holding first free chapter: "
                    f"{ctx.get('title', '')} / {ctx.get('chapter', '')} / {guid}. "
                    "announce_first_chapter_release is false."
                )
                continue
            
            title = ctx["title"]
            chapter = ctx["chapter"]
            updated_titles.add((title, host))
            
            ctx.update({
                "chapter_mention": mention_line,
                "global_mention": GLOBAL_MENTION,
                "translator_url": (
                    ctx.get("translator_url", "")
                    or get_translator_url(ctx.get("host", ""), ctx.get("title", ""))
                    or TRANSLATOR_URL
                ),
            })
            
            payload = render_message("free_chapters", ctx)
            kwargs = to_discord_py_kwargs(payload)
            
            await channel.send(**kwargs)

            print(f"📨 Sent: {chapter} / {guid}")

            # mark as seen and bump time (timezone-aware)
            norm = normalize_guid(entry)
            state[SEEN_KEY].append(norm)
            seen.add(guid_key)
            dt = parse_pub_iso(entry) or datetime.now(timezone.utc)
            state[LAST_POST_TIME] = dt.isoformat()
            save_state(state)

            new_last = raw_guid_from_entry(entry)

        if new_last and new_last != state.get(FEED_KEY):
            state[FEED_KEY] = new_last
            save_state(state)
            print(f"💾 Updated {STATE_FILE}[\"{FEED_KEY}\"] → {new_last}")

        # 🔔 trigger once per novel
        for title, host in updated_titles:
            try:
                trigger_status_update(title, host)
            except Exception as exc:
                print(f"⚠️ Optional card status update crashed for {title}; skipped: {exc}")

        await asyncio.sleep(1)
        await bot.close()

    await bot.start(TOKEN)
    

if __name__ == "__main__":
    try:
        asyncio.run(send_new_entries())
    finally:
        commit_state_if_changed()