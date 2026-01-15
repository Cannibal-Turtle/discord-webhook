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

# ─── CONFIG ────────────────────────────────────────────────────────────────
TOKEN      = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_ADVANCE_CHAPTERS_CHANNEL"])

STATE_FILE = "state_rss.json"
FEED_KEY   = "paid_last_guid"
SEEN_KEY        = "seen_guids_paid"
LAST_POST_TIME  = "last_post_time_paid"
SEEN_CAP        = 500
TIME_BACKSTOP   = False

RSS_URL    = "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/paid_chapters_feed.xml"

GLOBAL_MENTION = "<@&1342484466043453511>"  # the always-ping role
NSFW_ROLE = "<@&1343352825811439616>"
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
    return (entry.get("discord_role_id") or "").strip()

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
    # host::guid  (guid unescaped, URL host lowercased if URL-like)
    host = (entry.get("host") or "").strip().lower()
    raw  = (entry.get("guid") or entry.get("id") or "").strip()
    raw  = html.unescape(raw)
    try:
        p = urlsplit(raw)
        if p.scheme and p.netloc:
            raw = urlunsplit((p.scheme, p.netloc.lower(), p.path, p.query, p.fragment))
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

    # custom discord emoji format
    m = re.match(r"^<(?P<anim>a?):(?P<name>[A-Za-z0-9_]+):(?P<id>\d+)>$", s)
    if m:
        animated = bool(m.group("anim"))
        name     = m.group("name")
        emoji_id = int(m.group("id"))
        return discord.PartialEmoji(
            name=name,
            id=emoji_id,
            animated=animated,
        )

    # fallback: maybe it's just a normal unicode emoji like "🔥"
    # heuristic: no '<' '>' ':' and not super long
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

    # 1) Try a leading custom emoji
    m = re.match(r"^\s*(<a?:[A-Za-z0-9_]+:\d+>)", s)
    if m:
        emoji_obj = parse_custom_emoji(m.group(1))
        s = s[m.end():]  # consume it
    else:
        # 2) Try a leading token as possible unicode emoji (🔥, etc.)
        m2 = re.match(r"^\s*(\S+)", s)
        if m2:
            tok = m2.group(1)
            maybe = parse_custom_emoji(tok)
            if maybe:
                emoji_obj = maybe
                s = s[m2.end():]  # consume it

    # 3) Find the first integer anywhere in the remaining string
    mnum = re.search(r"\d+", s)
    if mnum:
        label_text = mnum.group(0)

    if not label_text and not emoji_obj:
        label_text = "Read here"

    return label_text, emoji_obj


async def send_new_paid_entries():
    state   = load_state()
    last    = state.get(FEED_KEY)
    feed    = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest order

    seen = set(state.get(SEEN_KEY, []))
    last_post_time = state.get(LAST_POST_TIME)
    last_post_dt = dateparser.parse(last_post_time) if (TIME_BACKSTOP and last_post_time) else None
    
    to_send = []
    for e in entries:  # oldest → newest
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
    bot     = discord.Client(intents=intents)

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

            # --- pull metadata from the RSS entry ---
            host        = entry.get("host", "").strip()
            series_role = get_series_role(entry)
            nsfw_flag   = is_nsfw(entry)
            title_text  = entry.get("title","").strip()

            chaptername = entry.get("chaptername","").strip()
            nameextend  = entry.get("nameextend","").strip()

            link        = entry.get("link","").strip()
            translator  = entry.get("translator","").strip()

            thumb_url   = (entry.get("featuredImage") or {}).get("url") \
                          or (entry.get("featuredimage") or {}).get("url")
            host_logo   = (entry.get("hostLogo") or {}).get("url") \
                          or (entry.get("hostlogo") or {}).get("url")

            pubdate_raw = getattr(entry, "published", None)
            timestamp   = dateparser.parse(pubdate_raw) if pubdate_raw else None

            coin_label_raw = entry.get("coin","").strip()
            
            mention_line = _build_chapter_mention(
                series_role=series_role,
                nsfw=nsfw_flag,
                global_mention=GLOBAL_MENTION,
             )
            
            # --- top text with pings ---
            content = (
                f"{mention_line} <a:TurtleDance:1365253970435510293>\n"
                f"<a:1366_sweetpiano_happy:1368136820965249034> **{title_text}** <:pink_lock:1368266294855733291>"
            )

            # --- embed with chapter info ---
            embed = Embed(
                title=f"<a:moonandstars:1365569468629123184>**{chaptername}**",
                url=link,
                description=nameextend or discord.Embed.Empty,
                timestamp=timestamp,
                color=int("A87676", 16),  # dusty rose hex -> int
            )
            embed.set_author(name=f"{translator}˙ᵕ˙")
            if thumb_url:
                embed.set_thumbnail(url=thumb_url)
            embed.set_footer(text=host, icon_url=host_logo)

            # --- build the button row ---
            label_text, emoji_obj = get_coin_button_parts_from_feed(coin_label_raw)
            
            if not label_text and not emoji_obj:
                label_text = "Read here"

            btn = Button(
                label=label_text,
                url=link,
                emoji=emoji_obj  # PartialEmoji or unicode is fine
            )

            view = View()
            view.add_item(btn)

            # send
            await channel.send(content=content, embed=embed, view=view)
            print(f"📨 Sent paid: {chaptername} / {guid}")
            # mark as seen and bump time backstop
            norm = normalize_guid(entry)
            state[SEEN_KEY].append(norm)
            
            dt = parse_pub_iso(entry) or datetime.now(timezone.utc)
            state[LAST_POST_TIME] = dt.isoformat()
            
            save_state(state)
            
            new_last = guid
            
        # update the pointer (so we don't repost next run)
        if new_last and new_last != state.get(FEED_KEY):
            state[FEED_KEY] = new_last
            save_state(state)
            print(f"💾 Updated {STATE_FILE}[\"{FEED_KEY}\"] → {new_last}")

        await asyncio.sleep(1)
        await bot.close()

    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(send_new_paid_entries())
