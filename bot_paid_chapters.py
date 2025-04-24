import os
import json
import asyncio
import feedparser
from datetime import datetime
from dateutil import parser as dateparser

import discord
from discord import Embed
from discord.ui import View, Button

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN           = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID      = int(os.environ["DISCORD_ADVANCE_CHAPTERS_CHANNEL"])
STATE_FILE      = "state_paid_chapters.json"
RSS_URL         = "https://cannibal-turtle.github.io/rss-feed/paid_chapters_feed.xml"

# the “always-mention” role you set in MonitoRSS
GLOBAL_MENTION = "<@&1342484466043453511>"
# ────────────────────────────────────────────────────────────────────────────────

def load_state():
    """
    Load the JSON state file, or reinitialize it if missing/corrupt.
    Returns a dict with at least "last_guid".
    """
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Either no file yet, or it’s malformed/empty → recreate it
        initial = {"last_guid": None}
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(initial, f, indent=2, ensure_ascii=False)
        return initial

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

async def send_new_paid_entries():
    state = load_state()
    feed = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest

    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        channel = bot.get_channel(CHANNEL_ID)
        if channel is None:
            print(f"❌ Cannot find channel {CHANNEL_ID}")
            await bot.close()
            return

        # 1) Prepare chronological slice (oldest → newest)
        guids = [(e.get("guid") or e.get("id")) for e in entries]
        last  = state.get("last_guid")
        if last in guids:
            idx     = guids.index(last)
            to_send = entries[idx+1:]
        else:
            to_send = entries

        # 2) Send only the new entries, in order
        new_last = last
        for entry in to_send:
            guid = entry.get("guid") or entry.get("id")

            # ── Content (with 🔒) ───────────────────────────────────────
            role_id = entry.get("discord_role_id", "").strip()
            title   = entry.get("title", "").strip()
            content = f"{role_id} | {GLOBAL_MENTION}\n**{title}**  🔒"

            # ── Embed ─────────────────────────────────────────────────
            chaptername = entry.get("chaptername", "").strip()
            nameextend  = entry.get("nameextend", "").strip()
            link        = entry.get("link", "").strip()
            translator  = entry.get("translator", "").strip()
            thumb_url   = (entry.get("featuredImage") or entry.get("featuredimage") or {}).get("url")
            host        = entry.get("host", "").strip()
            host_logo   = (entry.get("hostLogo") or entry.get("hostlogo") or {}).get("url")
            pubdate_raw = getattr(entry, "published", None)
            timestamp   = dateparser.parse(pubdate_raw) if pubdate_raw else None

            embed = Embed(
                title=f"**{chaptername}**",
                url=link,
                description=nameextend or discord.Embed.Empty,
                timestamp=timestamp,
                color=int("A87676", 16),
            )
            embed.set_author(name=f"{translator}⋆. 𐙚")
            if thumb_url:
                embed.set_thumbnail(url=thumb_url)
            embed.set_footer(text=host, icon_url=host_logo)

            # ── Button (coin label) ────────────────────────────────────
            coin_label = entry.get("coin", "").strip()
            view = View()
            view.add_item(Button(label=coin_label or "Read here", url=link))

            # ── Send & track ─────────────────────────────────────────
            await channel.send(content=content, embed=embed, view=view)
            print(f"📨 Sent paid: {chaptername} / {guid}")

            new_last = guid

        # 3) Save checkpoint & exit
        if new_last and new_last != state.get("last_guid"):
            state["last_guid"] = new_last
            save_state(state)
            print(f"💾 Updated paid state.last_guid → {new_last}")

        await bot.close()

    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(send_new_paid_entries())
