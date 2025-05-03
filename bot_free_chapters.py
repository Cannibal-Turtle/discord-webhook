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
STATE_FILE      = "state_rss.json"
FEED_KEY        = "free_last_guid"
RSS_URL         = "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/free_chapters_feed.xml"

# a global “always-mention” role id you used in MonitoRSS
GLOBAL_MENTION = "<@&1342483851338846288>"
# ────────────────────────────────────────────────────────────────────────────────

def load_state():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        initial = {
          "free_last_guid":    None,
          "paid_last_guid":    None,
          "comments_last_guid": None
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(initial, f, indent=2, ensure_ascii=False)
        return initial

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

async def send_new_entries():
    state = load_state()
    last  = state.get(FEED_KEY)
    feed  = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest → newest

    # 1) Compute list of GUIDs & slice out only the new entries
    guids   = [(e.get("guid") or e.get("id")) for e in entries]
    if last in guids:
        to_send = entries[guids.index(last)+1:]
    else:
        to_send = entries

    # 2) Early exit if nothing new
    if not to_send:
        print("🛑 No new free chapters—skipping Discord login.")
        return

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
        last    = state.get(FEED_KEY)
        if last in guids:
            idx     = guids.index(last)
            to_send = entries[idx+1:]
        else:
            to_send = entries

        # 2) Send only those new entries
        new_last = last
        for entry in to_send:
            guid = entry.get("guid") or entry.get("id")

            # build content…
            role_id = entry.get("discord_role_id","").strip()
            title   = entry.get("title","").strip()
            content = (
                f"{role_id} | {GLOBAL_MENTION} <a:TurtleDance:1365253970435510293>\n"
                f"<a:5037sweetpianoyay:1368138418487427102> **{title}** <:pink_unlock:1368206247790383294>"
                )

            # build embed…
            chaptername = entry.get("chaptername","").strip()
            nameextend  = entry.get("nameextend","").strip()
            link        = entry.get("link","").strip()
            translator  = entry.get("translator","").strip()
            thumb_url   = (entry.get("featuredImage") or entry.get("featuredimage") or {}).get("url")
            host        = entry.get("host","").strip()   # ← make sure host is pulled here
            host_logo   = (entry.get("hostLogo") or entry.get("hostlogo") or {}).get("url")
            pubdate_raw = getattr(entry, "published", None)
            timestamp   = dateparser.parse(pubdate_raw) if pubdate_raw else None

            embed = Embed(
                title=f"<a:moonandstars:1365569468629123184>**{chaptername}**",
                url=link,
                description=nameextend or discord.Embed.Empty,
                timestamp=timestamp,
                color=int("FFF9BF", 16),
            )
            embed.set_author(name=f"{translator}˙ᵕ˙")
            if thumb_url:
                embed.set_thumbnail(url=thumb_url)
            embed.set_footer(text=host, icon_url=host_logo)

            # button & send…
            view = View()
            view.add_item(Button(label="Read here", url=link))
            await channel.send(content=content, embed=embed, view=view)
            print(f"📨 Sent: {chaptername} / {guid}")

            new_last = guid

        # 3) Save checkpoint & exit
        if new_last and new_last != state.get(FEED_KEY):
            state[FEED_KEY] = new_last
            save_state(state)
            print(f"💾 Updated {STATE_FILE} → {new_last}")

        await bot.close()

    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(send_new_entries())
