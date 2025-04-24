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
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE, encoding="utf-8"))
    return {"last_guid": None}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


async def send_new_entries():
    state = load_state()
    feed = feedparser.parse(RSS_URL)
    # entries come newest→oldest by default; reverse so we post oldest first
    entries = list(reversed(feed.entries))

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

        new_last = state.get("last_guid")
        for entry in entries:
            guid = entry.get("guid") or entry.get("id")
            if state["last_guid"] is not None and guid == state["last_guid"]:
                # we've caught up
                break

            # ── build content ─────────────────────────────────────────────────
            # MonitoRSS did: {{rss:discord_role_id__#}} | {{discord::mentions}}\n**{{title}}** 🔓
            role_id = entry.get("discord_role_id", "").strip()
            title   = entry.get("title", "").strip()
            content = f"{role_id} | {GLOBAL_MENTION}\n**{title}**  🔓"

            # ── build embed ────────────────────────────────────────────────────
            chaptername = entry.get("chaptername", "").strip()
            nameextend  = entry.get("nameextend", "").strip()
            link        = entry.get("link", "").strip()
            translator  = entry.get("translator", "").strip()
            thumb_url   = entry.get("featuredImage", {}).get("url") or entry.get("featuredimage", {}).get("url")
            host        = entry.get("host", "").strip()
            host_logo   = entry.get("hostLogo", {}).get("url") or entry.get("hostlogo", {}).get("url")
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
            embed.set_footer(text=host, icon_url=host_logo)

            # ── button ─────────────────────────────────────────────────────────
            view = View()
            view.add_item(
                Button(label="Read here", url=link)
            )

            # ── actually send it ────────────────────────────────────────────────
            await channel.send(content=content, embed=embed, view=view)
            print(f"📨 Sent: {chaptername} / {guid}")

            # track so we don’t repost
            new_last = guid

        # save updated state & shut down
        if new_last:
            state["last_guid"] = new_last
            save_state(state)
            print(f"💾 Updated state.last_guid → {new_last}")

        await bot.close()

    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(send_new_entries())
