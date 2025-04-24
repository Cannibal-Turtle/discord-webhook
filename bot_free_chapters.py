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
CHANNEL_ID      = int(os.environ["DISCORD_FREE_CHAPTERS_CHANNEL"])
STATE_FILE      = "state_free_chapters.json"
RSS_URL         = "https://cannibal-turtle.github.io/rss-feed/free_chapters_feed.xml"

# a global “always-mention” role id you used in MonitoRSS
GLOBAL_MENTION = "<@&1342483851338846288>"
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

async def send_new_entries():
    state = load_state()
    feed  = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest

    # discord.py setup
    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        channel = bot.get_channel(CHANNEL_ID)
        if channel is None:
            print(f"❌ Cannot find channel {CHANNEL_ID}")
            await bot.close()
            return

        # 1) Prepare chronological slice
        guids   = [(e.get("guid") or e.get("id")) for e in entries]
        last    = state.get("last_guid")
        if last in guids:
            idx     = guids.index(last)
            to_send = entries[idx+1:]
        else:
            to_send = entries

        # 2) Send only those new entries
        new_last = state.get("last_guid")
        for entry in to_send:
            guid = entry.get("guid") or entry.get("id")

            # build content…
            role_id = entry.get("discord_role_id","").strip()
            title   = entry.get("title","").strip()
            content = f"{role_id} | {GLOBAL_MENTION}\n**{title}**  🔓"

            # build embed…
            chaptername = entry.get("chaptername","").strip()
            nameextend  = entry.get("nameextend","").strip()
            link        = entry.get("link","").strip()
            translator  = entry.get("translator","").strip()
            thumb_url   = (entry.get("featuredImage") or entry.get("featuredimage") or {}).get("url")
            host        = entry.get("host","").strip()   # ← make sure host is pulled here
            host_logo   = (entry.get("hostLogo") or entry.get("hostlogo") or {}).get("url")
            pubdate_raw = entry.get("pubDate") or entry.get("pubdate")
            timestamp   = dateparser.parse(pubdate_raw) if pubdate_raw else None

            embed = Embed(
                title=f"**{chaptername}**",
                url=link,
                description=nameextend or discord.Embed.Empty,
                timestamp=timestamp,
                color=int("FFF9BF", 16),
            )
            embed.set_author(name=f"{translator}⋆. 𐙚")
            if thumb_url:
                embed.set_thumbnail(url=thumb_url)

            # ── FOOTER: host + static date “Wed, 23 Apr 2025” ─────────────
            # Format timestamp to exactly Day, DD Mon YYYY
            date_only = timestamp.strftime("%a, %d %b %Y") if timestamp else ""
            footer_txt = f"{host} | {date_only}"
            embed.set_footer(text=footer_txt, icon_url=host_logo)

            # button & send…
            view = View()
            view.add_item(Button(label="Read here", url=link))
            await channel.send(content=content, embed=embed, view=view)
            print(f"📨 Sent: {chaptername} / {guid}")

            new_last = guid

        # 3) Save checkpoint & exit
        if new_last and new_last != state.get("last_guid"):
            state["last_guid"] = new_last
            save_state(state)
            print(f"💾 Updated state.last_guid → {new_last}")

        await bot.close()

    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(send_new_entries())
