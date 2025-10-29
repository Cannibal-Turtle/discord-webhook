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
    Convert "<:mistmint_currency:1433046707121422487>" or "<a:wiggle:...>"
    into discord.PartialEmoji(...).
    If it's just a unicode emoji like "🔥", return that string.
    Otherwise return None.
    """
    if not e:
        return None

    s = e.strip()

    # match custom emoji <...> form
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

    # maybe it's plain unicode
    if "<" not in s and ">" not in s and ":" not in s and len(s) <= 8:
        return s

    return None


def get_coin_button_parts(host: str, novel_title: str, fallback_price: str, fallback_emoji=None):
    """
    Look up coin_price and coin_emoji in HOSTING_SITE_DATA for this host+novel.

    Returns (label_text, emoji_for_button)

    label_text: "5"
    emoji_for_button: PartialEmoji | unicode | None
    """
    host_block = HOSTING_SITE_DATA.get(host, {})
    novels     = host_block.get("novels", {})
    details    = novels.get(novel_title, {})

    # price text (exposed on button as label)
    price_str = str(details.get("coin_price", fallback_price or "")).strip()

    # emoji source priority:
    # novel.coin_emoji > host.coin_emoji > fallback_emoji
    emoji_raw = (
        details.get("coin_emoji")
        or host_block.get("coin_emoji")
        or fallback_emoji
        or ""
    )
    emoji_obj = parse_custom_emoji(emoji_raw)

    return price_str, emoji_obj


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
