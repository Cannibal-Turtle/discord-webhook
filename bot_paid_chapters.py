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
SEEN_KEY   = "seen_guids_paid"
LAST_POST_TIME = "last_post_time_paid"
SEEN_CAP   = 500
TIME_BACKSTOP = True

RSS_URL = "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/paid_chapters_feed.xml"

GLOBAL_MENTION = "<@&1342484466043453511>"
NSFW_ROLE      = "<@&1343352825811439616>"
# ──────────────────────────────────────────────────────────────────────────


# ─── STATE ────────────────────────────────────────────────────────────────
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        st = {}

    st.setdefault(FEED_KEY, None)
    st.setdefault(SEEN_KEY, [])
    st.setdefault(LAST_POST_TIME, None)

    return st


def save_state(state):
    if len(state[SEEN_KEY]) > SEEN_CAP:
        state[SEEN_KEY] = state[SEEN_KEY][-SEEN_CAP:]

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ─── HELPERS ──────────────────────────────────────────────────────────────
def normalize_guid(entry):
    host = (entry.get("host") or "").strip().lower()

    if getattr(entry, "guid", None):
        raw = entry.guid
    elif getattr(entry, "id", None):
        raw = entry.id
    else:
        raw = ""

    raw = html.unescape(raw).strip()

    try:
        p = urlsplit(raw)
        if p.scheme and p.netloc:
            raw = urlunsplit((p.scheme, p.netloc.lower(), p.path, p.query, p.fragment))
    except Exception:
        pass

    return f"{host}::{raw}"


def parse_pub_dt(entry):
    raw = getattr(entry, "published", None)
    if not raw:
        return None
    try:
        return dateparser.parse(raw)
    except Exception:
        return None


def is_nsfw(entry):
    return (entry.get("category") or "").strip().upper() == "NSFW"


def get_series_role(entry):
    return (entry.get("discord_role_id") or "").strip()


def join_mentions(*parts):
    seen = set()
    out = []
    for p in parts:
        if not p:
            continue
        for seg in re.split(r"[| ]+", p):
            seg = seg.strip()
            if seg and seg not in seen:
                seen.add(seg)
                out.append(seg)
    return " | ".join(out)


def parse_custom_emoji(s):
    if not s:
        return None

    s = s.strip()
    m = re.match(r"^<(?P<a>a?):(?P<n>[A-Za-z0-9_]+):(?P<i>\d+)>$", s)
    if m:
        return discord.PartialEmoji(
            name=m.group("n"),
            id=int(m.group("i")),
            animated=bool(m.group("a")),
        )

    if "<" not in s and ">" not in s and ":" not in s and len(s) <= 8:
        return s

    return None


def parse_coin(coin_text):
    if not coin_text:
        return "Read here", None

    coin_text = coin_text.strip()
    emoji = None

    m = re.match(r"^\s*(<a?:[A-Za-z0-9_]+:\d+>)", coin_text)
    if m:
        emoji = parse_custom_emoji(m.group(1))
        coin_text = coin_text[m.end():]
    else:
        tok = coin_text.split()[0]
        maybe = parse_custom_emoji(tok)
        if maybe:
            emoji = maybe
            coin_text = coin_text[len(tok):]

    num = re.search(r"\d+", coin_text)
    label = num.group(0) if num else "Read here"

    return label, emoji


# ─── MAIN ─────────────────────────────────────────────────────────────────
async def send_new_paid_entries():
    state = load_state()
    seen  = set(state[SEEN_KEY])

    last_post_dt = None
    if TIME_BACKSTOP and state[LAST_POST_TIME]:
        last_post_dt = dateparser.parse(state[LAST_POST_TIME])

    feed = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest

    to_send = []
    for e in entries:
        norm = normalize_guid(e)
        if norm in seen:
            continue

        dt = parse_pub_dt(e)
        if last_post_dt and dt and dt <= last_post_dt:
            continue

        to_send.append(e)

    if not to_send:
        print("🛑 No new paid chapters.")
        return

    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            print("❌ Channel not found")
            await bot.close()
            return

        max_dt = last_post_dt
        last_guid = state.get(FEED_KEY)

        for entry in to_send:
            title = entry.get("title", "").strip()
            chapter = entry.get("chaptername", "").strip()
            nameextend = entry.get("nameextend", "").strip()
            link = entry.get("link", "").strip()
            translator = entry.get("translator", "").strip()
            host = entry.get("host", "").strip()

            mention = join_mentions(
                get_series_role(entry),
                NSFW_ROLE if is_nsfw(entry) else None,
                GLOBAL_MENTION,
            )

            content = (
                f"{mention}\n"
                f"**{title}**"
            )

            embed = Embed(
                title=chapter,
                url=link,
                description=nameextend or discord.Embed.Empty,
                color=int("A87676", 16),
            )

            dt = parse_pub_dt(entry)
            if dt:
                embed.timestamp = dt
                if not max_dt or dt > max_dt:
                    max_dt = dt

            embed.set_author(name=f"{translator}˙ᵕ˙")

            thumb = (entry.get("featuredImage") or {}).get("url")
            if thumb:
                embed.set_thumbnail(url=thumb)

            embed.set_footer(
                text=host,
                icon_url=(entry.get("hostLogo") or {}).get("url"),
            )

            label, emoji = parse_coin(entry.get("coin", ""))
            view = View()
            view.add_item(Button(label=label, url=link, emoji=emoji))

            await channel.send(content=content, embed=embed, view=view)

            norm = normalize_guid(entry)
            seen.add(norm)
            state[SEEN_KEY].append(norm)
            last_guid = entry.get("guid") or entry.get("id")

        # ── COMMIT STATE ONCE ──
        if max_dt:
            state[LAST_POST_TIME] = max_dt.isoformat()
        state[FEED_KEY] = last_guid

        save_state(state)
        print(f"✅ Posted {len(to_send)} paid chapters")

        await bot.close()

    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(send_new_paid_entries())
