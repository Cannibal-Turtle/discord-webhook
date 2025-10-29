import os
import json
import asyncio
import feedparser
from dateutil import parser as dateparser

import discord
from discord import Embed
from discord.ui import View, Button

# pull mapping info so we can get coin_emoji / coin_price
from novel_mappings import HOSTING_SITE_DATA

# ─── CONFIG ────────────────────────────────────────────────────────────────
TOKEN      = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_ADVANCE_CHAPTERS_CHANNEL"])

STATE_FILE = "state_rss.json"
FEED_KEY   = "paid_last_guid"

RSS_URL    = "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/paid_chapters_feed.xml"

GLOBAL_MENTION = "<@&1342484466043453511>"  # your always-ping role

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
    Take a custom emoji string like '<:mistmint_currency:1433046707121422487>'
    and return discord.PartialEmoji(name='mistmint_currency', id=1433046707121422487)

    If it's not that format, return None.
    """
    if not e:
        return None
    e = e.strip()

    # match <:name:id>  OR <a:name:id> (animated)
    # groups:
    #   animated? (a: optional)
    #   name
    #   id
    import re
    m = re.match(r"^<a?:([A-Za-z0-9_]+):([0-9]+)>$", e)
    if not m:
        # might be a plain unicode emoji like "🔥"
        # discord.py lets you just pass the raw unicode char as emoji kwarg,
        # so we can just return the string for unicode.
        # quick heuristic: if it has no '<' and no ':' and length <= 4-ish,
        # assume it's unicode.
        if "<" not in e and ":" not in e and len(e) <= 8:
            return e
        return None

    name = m.group(1)
    _id  = int(m.group(2))
    return discord.PartialEmoji(name=name, id=_id)


def get_coin_button_parts(host: str, novel_title: str, fallback_price: str, fallback_emoji=None):
    """
    Look up coin_price and coin_emoji in HOSTING_SITE_DATA for this host+novel.

    Return (label_text, emoji_obj_for_button)

    - label_text: e.g. "5"
    - emoji_obj_for_button: discord.PartialEmoji(...) or unicode emoji or None
    """
    host_block = HOSTING_SITE_DATA.get(host, {})
    novels     = host_block.get("novels", {})
    details    = novels.get(novel_title, {})

    # price label
    price_str = str(details.get("coin_price", fallback_price or "")).strip()

    # emoji field
    emoji_raw = details.get("coin_emoji", fallback_emoji)
    emoji_obj = parse_custom_emoji(emoji_raw) if emoji_raw else None

    return price_str, emoji_obj


async def send_new_paid_entries():
    state   = load_state()
    last    = state.get(FEED_KEY)
    feed    = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest

    # figure out what we haven't posted yet
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
            guid        = entry.get("guid") or entry.get("id")

            # --- pull metadata from feed item ---
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

            # chapter cost
            coin_label_raw = entry.get("coin","").strip()

            # --- build the ping content line ---
            content = (
                f"{role_id} | {GLOBAL_MENTION} <a:TurtleDance:1365253970435510293>\n"
                f"<a:1366_sweetpiano_happy:1368136820965249034> **{title_text}** <:pink_lock:1368266294855733291>"
            )

            # --- build the embed (chapter info box) ---
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
            # we want: [ <emoji> <coin price> ] that links to chapter.
            # the emoji + price depend on host/novel mapping.
            label_text, emoji_obj = get_coin_button_parts(
                host=host,
                novel_title=novel_title,
                fallback_price=coin_label_raw,    # from feed <coin>
                fallback_emoji=None               # feed doesn't send coin_emoji yet
            )

            # if we somehow have neither price nor emoji, fall back to "Read here"
            if not label_text and not emoji_obj:
                label_text = "Read here"

            # Make the view / button
            view = View()
            # discord.ui.Button for link-style buttons: give url=..., style auto Link
            view.add_item(
                Button(
                    label=label_text,
                    url=link,
                    emoji=emoji_obj  # can be PartialEmoji or unicode
                )
            )

            # --- send message ---
            await channel.send(content=content, embed=embed, view=view)
            print(f"📨 Sent paid: {chaptername} / {guid}")
            new_last = guid

        # update pointer
        if new_last and new_last != state.get(FEED_KEY):
            state[FEED_KEY] = new_last
            save_state(state)
            print(f"💾 Updated {STATE_FILE}[\"{FEED_KEY}\"] → {new_last}")

        await asyncio.sleep(1)
        await bot.close()

    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(send_new_paid_entries())
