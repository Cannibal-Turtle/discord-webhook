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
from discord import Embed
from discord.ui import View, Button
import requests

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN           = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID      = int(os.environ["DISCORD_FREE_CHAPTERS_CHANNEL"])
STATE_FILE      = "state_rss.json"
FEED_KEY        = "free_last_guid"
RSS_URL         = "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/free_chapters_feed.xml"
SEEN_KEY        = "seen_guids_free"
LAST_POST_TIME  = "last_post_time_free"
SEEN_CAP        = 500
TIME_BACKSTOP   = True

GLOBAL_MENTION  = "<@&1342483851338846288>"   # always-mention role
NSFW_ROLE       = "<@&1343352825811439616>"
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
    # your feed stores a full mention like "<@&123...>" inside CDATA; just strip it
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
    """
    Compose: <series role> [| <NSFW_ROLE>] | <GLOBAL_MENTION>
    If series_role is empty, you’ll just get: <GLOBAL_MENTION>.
    """
    nsfw_tail = NSFW_ROLE if nsfw else None
    return _join_role_mentions(series_role, nsfw_tail, global_mention)

def normalize_guid(entry):
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

async def send_new_entries():
    state = load_state()
    last  = state.get(FEED_KEY)
    feed  = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest

    seen = set(state.get(SEEN_KEY, []))
    last_post_time = state.get(LAST_POST_TIME)
    last_post_dt = dateparser.parse(last_post_time) if (TIME_BACKSTOP and last_post_time) else None

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

            title   = (entry.get("title") or "").strip()
            updated_titles.add((title, host))

            content = (
                f"{mention_line} <a:TurtleDance:1365253970435510293>\n"
                f"<a:5037sweetpianoyay:1368138418487427102> **{title}** <:pink_unlock:1368266307824255026>"
            )

            # Embed fields
            chaptername = (entry.get("chaptername") or "").strip() or "New Chapter"
            nameextend  = (entry.get("nameextend") or "").strip()
            link        = (entry.get("link") or "").strip()
            translator  = (entry.get("translator") or "").strip()
            # featured image shape differs sometimes; try both
            fi = entry.get("featuredImage") or entry.get("featuredimage") or {}
            thumb_url   = (fi or {}).get("url")
            hl = entry.get("hostLogo") or entry.get("hostlogo") or {}
            host_logo   = (hl or {}).get("url")

            pubdate_raw = getattr(entry, "published", None)
            timestamp   = dateparser.parse(pubdate_raw) if pubdate_raw else None

            embed = Embed(
                title=f"<a:moonandstars:1365569468629123184>**{chaptername}**",
                url=link,
                timestamp=timestamp,
                color=int("FFF9BF", 16),
            )
            
            if nameextend:
                embed.description = nameextend

            embed.set_author(name=f"{translator}˙ᵕ˙")
            if thumb_url:
                embed.set_thumbnail(url=thumb_url)
            embed.set_footer(text=host, icon_url=host_logo)

            # Button & send
            view = View()
            view.add_item(Button(label="Read here", url=link))
            await channel.send(content=content, embed=embed, view=view)

            print(f"📨 Sent: {chaptername} / {guid}")

            # mark as seen and bump time (timezone-aware)
            norm = normalize_guid(entry)
            state[SEEN_KEY].append(norm)
            dt = parse_pub_iso(entry) or datetime.now(timezone.utc)
            state[LAST_POST_TIME] = dt.isoformat()
            save_state(state)

            new_last = guid

        if new_last and new_last != state.get(FEED_KEY):
            state[FEED_KEY] = new_last
            save_state(state)
            print(f"💾 Updated {STATE_FILE}[\"{FEED_KEY}\"] → {new_last}")

        # 🔔 trigger once per novel
        for title, host in updated_titles:
            print(f"🔔 Triggering status update for {title} ({host})")
            trigger_status_update(title, host)

        await asyncio.sleep(1)
        await bot.close()

    await bot.start(TOKEN)

def trigger_status_update(title: str, host: str):
    url = "https://api.github.com/repos/Cannibal-Turtle/rss-feed/dispatches"
    headers = {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }
    payload = {
        "event_type": "update-novel-status",
        "client_payload": {
            "title": title,
            "host": host,
            "source": "free_chapter"
        }
    }

    r = requests.post(url, headers=headers, json=payload, timeout=10)
    if r.status_code >= 300:
        print(f"❌ Dispatch failed for {title}: {r.status_code} {r.text}")

if __name__ == "__main__":
    asyncio.run(send_new_entries())
