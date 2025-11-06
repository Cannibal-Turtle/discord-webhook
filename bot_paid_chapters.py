import os
import json
import asyncio
import re
import feedparser
from dateutil import parser as dateparser
import html
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timezone
import aiohttp
from io import BytesIO
import discord
from discord import Embed
from discord.ui import View, Button

from novel_mappings import HOSTING_SITE_DATA, get_nsfw_novels

# ─── CONFIG ────────────────────────────────────────────────────────────────
TOKEN      = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_ADVANCE_CHAPTERS_CHANNEL"])

STATE_FILE = "state_rss.json"
FEED_KEY   = "paid_last_guid"
SEEN_KEY        = "seen_guids_paid"
LAST_POST_TIME  = "last_post_time_paid"
SEEN_CAP        = 500
TIME_BACKSTOP   = True

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

def _build_chapter_mention(series_role: str, novel_title: str, global_mention: str) -> str:
    """
    Compose: <series role> [| <NSFW>] | <GLOBAL_MENTION>
    If series_role is empty, you’ll just get: <GLOBAL_MENTION>.
    """
    nsfw_tail = NSFW_ROLE if novel_title in get_nsfw_novels() else None
    # order changed: series → nsfw? → global
    return _join_role_mentions(series_role, nsfw_tail, global_mention)

async def spoiler_attachment_from_url(sess: aiohttp.ClientSession, url: str, fallback_name: str = "image.jpg"):
    if not url:
        return None, None
    name = fallback_name.rsplit("/", 1)[-1]
    if "." not in name:
        name += ".jpg"
    attach_name = f"SPOILER_{name}"
    try:
        async with sess.get(url, timeout=20) as r:
            if r.status != 200:
                return None, None
            b = await r.read()
        return discord.File(BytesIO(b), filename=attach_name), attach_name
    except Exception:
        return None, None

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


def get_coin_button_parts(host: str,
                          novel_title: str,
                          fallback_price: str,
                          fallback_emoji: str = None):
    """
    Decide what the paid button should show.

    We try to pull data from HOSTING_SITE_DATA, but we ALSO try to parse
    the <coin> field from the feed itself as a backup.

    Returns (label_text, emoji_for_button)

    - label_text -> string that becomes Button(label=...)
                    (ex: "5" or "Read here")
    - emoji_for_button -> PartialEmoji | unicode | None
                          (goes to Button(emoji=...))
    """

    # ----- 1. Start with completely empty defaults
    label_text   = ""
    emoji_obj    = None

    # ----- 2. Try mapping first (preferred)
    try:
        host_block = HOSTING_SITE_DATA.get(host, {})
        novels     = host_block.get("novels", {})
        details    = novels.get(novel_title, {})

        # coin_price from mapping (ex: 5)
        mapped_price = details.get("coin_price")
        if mapped_price is not None:
            label_text = str(mapped_price).strip()

        # coin_emoji priority: per-novel > per-host
        mapped_emoji_raw = (
            details.get("coin_emoji")
            or host_block.get("coin_emoji")
            or fallback_emoji
            or ""
        )
        emoji_obj = parse_custom_emoji(mapped_emoji_raw)
    except Exception:
        # if HOSTING_SITE_DATA wasn't imported or something exploded,
        # we silently fall back to feed parsing next
        pass

    # ----- 3. If still missing either emoji or price, try to steal it from the RSS <coin> text
    # fallback_price is literally entry.get("coin") from the feed,
    # which might look like "<:mint:12345> 5" all in one string.
    coin_text = (fallback_price or "").strip()

    if coin_text:
        # try to grab an emoji and/or number from that string
        # pattern: optional custom emoji + optional number
        # e.g. "<:mistmint_currency:1433046707121422487> 5"
        m = re.match(
            r"^(?P<emoji><a?:[A-Za-z0-9_]+:\d+>)?\s*(?P<num>\d+)?",
            coin_text
        )
        if m:
            # only fill fields we *don't* already have
            if not emoji_obj:
                emoji_raw_from_feed = (m.group("emoji") or "").strip()
                emoji_obj = parse_custom_emoji(emoji_raw_from_feed)

            if not label_text:
                num = (m.group("num") or "").strip()
                if num:
                    label_text = num

    # ----- 4. Absolute last safety net
    if not label_text and not emoji_obj:
        # we have literally nothing -> generic fallback
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
    
        # Reuse one HTTP session for all spoiler downloads
        async with aiohttp.ClientSession() as sess:
            for entry in to_send:
                guid = entry.get("guid") or entry.get("id")
    
                # --- pull metadata from the RSS entry ---
                novel_title = (entry.get("title") or "").strip()   # paid feed uses <title> for novel
                host        = (entry.get("host") or "").strip()
    
                series_role = (entry.get("discord_role_id") or "").strip()
                if not series_role:
                    series_role = (
                        HOSTING_SITE_DATA.get(host, {})
                                         .get("novels", {})
                                         .get(novel_title, {})
                                         .get("discord_role_id", "")
                        or ""
                    ).strip()
    
                title_text  = (entry.get("title") or "").strip()
                chaptername = (entry.get("chaptername") or "").strip()
                nameextend  = (entry.get("nameextend") or "").strip()
                link        = (entry.get("link") or "").strip()
                translator  = (entry.get("translator") or "").strip()
    
                fi = entry.get("featuredImage") or entry.get("featuredimage") or {}
                thumb_url = (fi or {}).get("url")
                hl = entry.get("hostLogo") or entry.get("hostlogo") or {}
                host_logo = (hl or {}).get("url")
    
                pubdate_raw = getattr(entry, "published", None)
                timestamp   = dateparser.parse(pubdate_raw) if pubdate_raw else None
    
                coin_label_raw = (entry.get("coin") or "").strip()
    
                mention_line = _build_chapter_mention(
                    series_role=series_role,
                    novel_title=novel_title,
                    global_mention=GLOBAL_MENTION,
                )
    
                content = (
                    f"{mention_line} <a:TurtleDance:1365253970435510293>\n"
                    f"<a:1366_sweetpiano_happy:1368136820965249034> **{title_text}** <:pink_lock:1368266294855733291>"
                )
    
                embed = Embed(
                    title=f"<a:moonandstars:1365569468629123184>**{chaptername}**",
                    url=link,
                    description=nameextend or discord.Embed.Empty,
                    timestamp=timestamp,
                    color=int("A87676", 16),
                )
                embed.set_author(name=f"{translator}˙ᵕ˙")
    
                # --- spoiler-aware thumbnail for NSFW novels ---
                files = []
                if novel_title in get_nsfw_novels():
                    file_obj, attach_name = await spoiler_attachment_from_url(sess, thumb_url, "thumb.jpg")
                    if file_obj:
                        files.append(file_obj)
                        embed.set_thumbnail(url=f"attachment://{attach_name}")
                    elif thumb_url:
                        embed.set_thumbnail(url=thumb_url)  # fallback (no blur)
                else:
                    if thumb_url:
                        embed.set_thumbnail(url=thumb_url)
    
                embed.set_footer(text=host, icon_url=host_logo)
    
                # --- paid button (your existing logic) ---
                label_text, emoji_obj = get_coin_button_parts(
                    host=host,
                    novel_title=novel_title,
                    fallback_price=coin_label_raw,
                    fallback_emoji=None,
                )
                if not label_text and not emoji_obj:
                    label_text = "Read here"
    
                view = View()
                view.add_item(Button(label=label_text, url=link, emoji=emoji_obj))
    
                # send (include files if any)
                await channel.send(content=content, embed=embed, view=view, files=files or None)
                print(f"📨 Sent paid: {chaptername} / {guid}")
    
                # mark as seen and bump time
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
    
        await asyncio.sleep(1)
        await bot.close()

    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(send_new_paid_entries())
