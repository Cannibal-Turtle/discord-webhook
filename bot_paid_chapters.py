import os
import json
import asyncio
import re
import feedparser
from dateutil import parser as dateparser

import discord
from discord import Embed
from discord.ui import View, Button

from novel_mappings import HOSTING_SITE_DATA

# ─── CONFIG ────────────────────────────────────────────────────────────────
TOKEN      = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_ADVANCE_CHAPTERS_CHANNEL"])

STATE_FILE = "state_rss.json"
FEED_KEY   = "paid_last_guid"

RSS_URL    = "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/paid_chapters_feed.xml"

GLOBAL_MENTION = "<@&1342484466043453511>"  # the always-ping role
# ──────────────────────────────────────────────────────────────────────────


def load_state():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        initial = {
            "free_last_guid":     None,
            "paid_last_guid":     None,
            "comments_last_guid": None
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(initial, f, indent=2, ensure_ascii=False)
        return initial


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


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

    # find which entries are new since last guid we posted
    guids = [(e.get("guid") or e.get("id")) for e in entries]
    if last in guids:
        to_send = entries[guids.index(last) + 1 :]
    else:
        to_send = entries

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
            novel_title = entry.get("novel_title", "").strip()
            host        = entry.get("host", "").strip()

            role_id     = entry.get("discord_role_id","").strip()
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

            # --- top text with pings ---
            content = (
                f"{role_id} | {GLOBAL_MENTION} <a:TurtleDance:1365253970435510293>\n"
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
            label_text, emoji_obj = get_coin_button_parts(
                host=host,
                novel_title=novel_title,
                fallback_price=coin_label_raw,
                fallback_emoji=None,
            )

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
