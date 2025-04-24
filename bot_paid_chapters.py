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
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE, encoding="utf-8"))
    return {"last_guid": None}


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

        new_last = state.get("last_guid")
        for entry in entries:
            guid = entry.get("guid") or entry.get("id")
            if state["last_guid"] is not None and guid == state["last_guid"]:
                break

            # ── Content (with 🔒) ───────────────────────────────────────────
            role_id = entry.get("discord_role_id", "").strip()
            title   = entry.get("title", "").strip()
            content = f"{role_id} | {GLOBAL_MENTION}\n**{title}**  🔒"

            # ── Embed ────────────────────────────────────────────────────────
            chaptername = entry.get("chaptername", "").strip()
            nameextend  = entry.get("nameextend", "").strip()
            link        = entry.get("link", "").strip()
            translator  = entry.get("translator", "").strip()
            thumb_url   = (entry.get("featuredImage") or entry.get("featuredimage") or {}).get("url")
            host        = entry.get("host", "").strip()
            host_logo   = (entry.get("hostLogo") or entry.get("hostlogo") or {}).get("url")
            pubdate_raw = entry.get("pubDate") or entry.get("pubdate")
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

            # ── Button (coin label) ─────────────────────────────────────────
            coin_label = entry.get("coin", "").strip()  # e.g. 🔥 5
            view = View()
            view.add_item(Button(label=coin_label or "Read here", url=link))

            # ── Send & track ────────────────────────────────────────────────
            await channel.send(content=content, embed=embed, view=view)
            print(f"📨 Sent paid: {chaptername} / {guid}")
            new_last = guid

        if new_last:
            state["last_guid"] = new_last
            save_state(state)
            print(f"💾 Updated paid state.last_guid → {new_last}")

        await bot.close()

    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(send_new_paid_entries())
