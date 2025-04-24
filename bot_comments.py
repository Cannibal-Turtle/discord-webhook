import os
import json
import asyncio
import feedparser
from dateutil import parser as dateparser

import discord
from discord import Embed

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN       = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID  = int(os.environ["DISCORD_COMMENTS_CHANNEL"])
STATE_FILE  = "state_comments.json"
RSS_URL     = "https://cannibal-turtle.github.io/rss-feed/aggregated_comments_feed.xml"
# ────────────────────────────────────────────────────────────────────────────────

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE, encoding="utf-8"))
    return {"last_guid": None}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

async def send_new_comments():
    state  = load_state()
    feed   = feedparser.parse(RSS_URL)
    # feed.entries is newest→oldest by default; reverse for oldest→newest
    entries = list(reversed(feed.entries))

    intents = discord.Intents.default()
    bot     = discord.Client(intents=intents)

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
                break  # no more new comments

            # ── Content ────────────────────────────────────────────────────────
            title       = entry.get("title", "").strip()
            role_id     = entry.get("discord_role_id", "").strip()
            content     = f"New comment for **{title}** || {role_id}"

            # ── Embed ──────────────────────────────────────────────────────────
            author      = entry.get("author") or entry.get("dc_creator", "")
            chapter     = entry.get("chapter", "").strip()
            comment_txt = entry.get("description", "").strip()
            reply_chain = entry.get("reply_chain", "").strip()  # placeholder fallback
            host        = entry.get("host", "").strip()
            host_logo   = (entry.get("hostLogo") or entry.get("hostlogo") or {}).get("url", "")
            pubdate_raw = entry.get("pubDate") or entry.get("pubdate")
            timestamp   = dateparser.parse(pubdate_raw) if pubdate_raw else None

            embed = Embed(
                title=f"❛❛{comment_txt}❜❜",
                description=reply_chain or discord.Embed.Empty,
                timestamp=timestamp,
                color=int("F0C7A4", 16),
            )
            embed.set_author(name=f"comment by {author} 🕊️ {chapter}")
            embed.set_footer(text=host, icon_url=host_logo)

            # ── Send & track ───────────────────────────────────────────────────
            await channel.send(content=content, embed=embed)
            print(f"📨 Sent comment: {guid}")
            new_last = guid

        if new_last:
            state["last_guid"] = new_last
            save_state(state)
            print(f"💾 Updated comments state.last_guid → {new_last}")

        await bot.close()

    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(send_new_comments())
