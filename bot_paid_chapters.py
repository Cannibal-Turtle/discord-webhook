import os
import json
import asyncio
import re
import feedparser
from dateutil import parser as dateparser
import html
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timezone

import discord
from discord import Embed
from discord.ui import View, Button

from message_context import build_feed_context
from message_renderer import render_message, to_discord_py_kwargs

# ─── CONFIG ────────────────────────────────────────────────────────────────
from config_loader import (
    get_novel_role_id,
    embed_value,
    embed_color,
    require_feed_value,
    require_feeds_value,
    require_file_value,
    require_role_value,
    role_id_to_mention,
)

TOKEN      = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_ADVANCE_CHAPTERS_CHANNEL"])

STATE_FILE = require_file_value("rss_state_path")
FEED_KEY   = require_feed_value("paid", "last_guid_key")
RSS_URL    = require_feed_value("paid", "url")

SEEN_KEY       = require_feed_value("paid", "seen_key")
LAST_POST_TIME = require_feed_value("paid", "last_post_time_key")
SEEN_CAP       = int(require_feeds_value("seen_cap"))
TIME_BACKSTOP  = bool(require_feeds_value("time_backstop"))

GLOBAL_MENTION = role_id_to_mention(require_role_value("paid_global"))
NSFW_ROLE      = role_id_to_mention(require_role_value("nsfw"))

AUTHOR_URL = str(embed_value("chapter_author_url", "")).strip()
# ──────────────────────────────────────────────────────────────────────────


def load_state():
    try:
        st = json.load(open(STATE_FILE, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        # first run / corrupted file -> seed with all keys, including the new ones
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

    # ── put the migration block HERE (existing state on disk) ──
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
    if isinstance(state.get(SEEN_KEY), list) and len(state[SEEN_KEY]) > SEEN_CAP:
        state[SEEN_KEY] = state[SEEN_KEY][-SEEN_CAP:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def is_nsfw(entry) -> bool:
    cat = (entry.get("category") or "").strip().upper()
    return cat == "NSFW"


def get_series_role(entry) -> str:
    short_code = (entry.get("short_code") or "").strip().upper()
    role_id = get_novel_role_id(short_code)
    return role_id_to_mention(role_id) if role_id else ""


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
    nsfw_tail = NSFW_ROLE if nsfw else None
    return _join_role_mentions(series_role, nsfw_tail, global_mention)


def normalize_guid(entry):
    host = (entry.get("host") or "").strip()
    raw = (entry.get("guid") or entry.get("id") or "").strip()
    raw = html.unescape(raw)

    try:
        p = urlsplit(raw)
        if p.scheme and p.netloc:
            raw = urlunsplit(
                (p.scheme, p.netloc.lower(), p.path, p.query, p.fragment)
            )
    except Exception:
        pass

    return f"{host}::{raw}"


def parse_pub_iso(entry):
    pub_raw = getattr(entry, "published", None)
    if not pub_raw:
        return None
    try:
        return dateparser.parse(pub_raw)
    except Exception:
        return None


def parse_custom_emoji(e: str):
    """
    Try to turn something like "<:mistmint_currency:1433046707121422487>"
    or "<a:dance:1234567890>" into a PartialEmoji that can be passed as
    Button(emoji=...).

    If it's plain unicode like "🔥", return the unicode string.
    If it's junk / empty, return None.
    """
    if not e:
        return None

    s = e.strip()

    m = re.match(
        r"^<(?P<anim>a?):(?P<name>[A-Za-z0-9_]+):(?P<id>\d+)>$",
        s
    )
    if m:
        animated = bool(m.group("anim"))
        name     = m.group("name")
        emoji_id = int(m.group("id"))
        return discord.PartialEmoji(
            name=name,
            id=emoji_id,
            animated=animated,
        )

    if "<" not in s and ">" not in s and ":" not in s and len(s) <= 8:
        return s

    return None


def get_coin_button_parts_from_feed(coin_text: str):
    """
    Parse <coin> like:
      "<:mistmint_currency:143...> 5", "🔥 5", "🔥5", "5"
    Return (label_text, emoji_obj_or_unicode).
    """
    s = (coin_text or "").strip()
    label_text = ""
    emoji_obj = None

    if not s:
        return "Read here", None

    m = re.match(r"^\s*(<a?:[A-Za-z0-9_]+:\d+>)", s)
    if m:
        emoji_obj = parse_custom_emoji(m.group(1))
        s = s[m.end():]
    else:
        m2 = re.match(r"^\s*(\S+)", s)
        if m2:
            tok = m2.group(1)
            maybe = parse_custom_emoji(tok)
            if maybe:
                emoji_obj = maybe
                s = s[m2.end():]

    mnum = re.search(r"\d+", s)
    if mnum:
        label_text = mnum.group(0)

    if not label_text and not emoji_obj:
        label_text = "Read here"

    return label_text, emoji_obj


async def send_new_paid_entries():
    state = load_state()
    last = state.get(FEED_KEY)

    feed = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest order

    seen = set(state.get(SEEN_KEY, []))
    last_post_time = state.get(LAST_POST_TIME)
    last_post_dt = (
        dateparser.parse(last_post_time)
        if (TIME_BACKSTOP and last_post_time)
        else None
    )

    to_send = []
    for e in entries:
        norm = normalize_guid(e)
        if norm in seen:
            continue
        if last_post_dt is not None:
            dt = parse_pub_iso(e)
            if dt and dt <= last_post_dt:
                continue
        to_send.append(e)

    if not to_send:
        print("🛑 No new paid chapters—skipping Discord login.")
        return

    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            print(f"❌ Cannot find channel {CHANNEL_ID}")
            await bot.close()
            return

        new_last = last

        for entry in to_send:
            guid = entry.get("guid") or entry.get("id")

            host = (entry.get("host") or "").strip()
            series_role = get_series_role(entry)
            nsfw_flag = is_nsfw(entry)
            
            mention_line = _build_chapter_mention(
                series_role=series_role,
                nsfw=nsfw_flag,
                global_mention=GLOBAL_MENTION,
            )
            
            ctx = build_feed_context(entry)
            
            label_text, emoji_obj = get_coin_button_parts_from_feed(ctx["coin"])
            
            ctx.update({
                "chapter_mention": mention_line,
                "global_mention": GLOBAL_MENTION,
                "chapter_author_url": AUTHOR_URL,
                "button_label": label_text,
                "button_emoji": str(emoji_obj or ""),
            })
            
            payload = render_message("paid_chapters", ctx)
            kwargs = to_discord_py_kwargs(payload)
            
            await channel.send(**kwargs)
            
            chapter = ctx["chapter"]
            print(f"📨 Sent paid: {chapter} / {guid}")

            norm = normalize_guid(entry)
            state[SEEN_KEY].append(norm)

            dt = parse_pub_iso(entry) or datetime.now(timezone.utc)
            state[LAST_POST_TIME] = dt.isoformat()

            save_state(state)
            new_last = guid

        if new_last and new_last != state.get(FEED_KEY):
            state[FEED_KEY] = new_last
            save_state(state)
            print(
                f"💾 Updated {STATE_FILE}[\"{FEED_KEY}\"] → {new_last}"
            )

        await asyncio.sleep(1)
        await bot.close()

    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(send_new_paid_entries())
