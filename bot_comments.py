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
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        initial = {"last_guid": None}
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(initial, f, indent=2, ensure_ascii=False)
        return initial

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
            
        # 1) Chronological order (oldest → newest)
        entries = list(reversed(feed.entries))
        
        # 2) Build GUID list and slice out only new entries
        guids   = [(e.get("guid") or e.get("id")) for e in entries]
        last    = state.get("last_guid")
        if last in guids:
            idx     = guids.index(last)
            to_send = entries[idx+1:]
        else:
            to_send = entries
        
        # 3) Post each new comment in order
        new_last = last
        for entry in to_send:
            guid        = entry.get("guid") or entry.get("id")
            title       = entry.get("title","").strip()
            role_id     = entry.get("discord_role_id","").strip()
            content     = f"New comment for **{title}** || {role_id}"
        
            author      = entry.get("author") or entry.get("dc_creator","")
            chapter     = entry.get("chapter","").strip()
            comment_txt = entry.get("description","").strip()
            reply_chain = entry.get("reply_chain","").strip()
            host        = entry.get("host","").strip()
            host_logo   = (entry.get("hostLogo") or entry.get("hostlogo") or {}).get("url","")
        
            # pull the real pubDate
            pubdate_raw = getattr(entry, "published", None)
            timestamp   = dateparser.parse(pubdate_raw) if pubdate_raw else None
        
            embed = Embed(
                title=f"❛❛{comment_txt}❜❜",
                description=reply_chain or discord.Embed.Empty,
                timestamp=timestamp,
                color=int("F0C7A4", 16),
            )
            embed.set_author(name=f"comment by {author} 🕊️ {chapter}")
            embed.set_footer(text=host, icon_url=host_logo)
        
            await channel.send(content=content, embed=embed)
            print(f"📨 Sent comment: {guid}")
            new_last = guid
        
        # 4) Commit the new checkpoint
        if new_last and new_last != state.get("last_guid"):
            state["last_guid"] = new_last
            save_state(state)
            print(f"💾 Updated comments state.last_guid → {new_last}")

        await bot.close()

    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(send_new_comments())
