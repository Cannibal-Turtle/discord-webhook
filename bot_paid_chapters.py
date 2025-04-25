import os
import json
import asyncio
import feedparser
from dateutil import parser as dateparser

import discord
from discord import Embed
from discord.ui import View, Button

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN           = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID      = int(os.environ["DISCORD_ADVANCE_CHAPTERS_CHANNEL"])
STATE_FILE      = "state_rss.json"
FEED_KEY        = "paid_last_guid"
RSS_URL         = "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/paid_chapters_feed.xml"

GLOBAL_MENTION  = "<@&1342484466043453511>"  # MonitoRSS “always-mention” role
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

async def send_new_paid_entries():
    state   = load_state()
    last    = state.get(FEED_KEY)
    feed    = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest→newest

    # 1) Compute list of GUIDs & slice out only the new entries
    guids   = [(e.get("guid") or e.get("id")) for e in entries]
    if last in guids:
        to_send = entries[guids.index(last)+1:]
    else:
        to_send = entries

    # 2) Early exit if nothing new
    if not to_send:
        print("🛑 No new paid chapters—skipping Discord login.")
        return

    # 3) Connect the bot only when there's something to post
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

            # build message content
            role_id     = entry.get("discord_role_id","").strip()
            title_text  = entry.get("title","").strip()
            content     = f"{role_id} | {GLOBAL_MENTION} <a:TurtleDance:1365253970435510293>\n**{title_text}**  🔒"

            # build embed
            chaptername = entry.get("chaptername","").strip()
            nameextend  = entry.get("nameextend","").strip()
            link        = entry.get("link","").strip()
            translator  = entry.get("translator","").strip()
            thumb_url   = (entry.get("featuredImage") or {}).get("url") \
                          or (entry.get("featuredimage") or {}).get("url")
            host        = entry.get("host","").strip()
            host_logo   = (entry.get("hostLogo") or {}).get("url") \
                          or (entry.get("hostlogo") or {}).get("url")
            pubdate_raw = getattr(entry, "published", None)
            timestamp   = dateparser.parse(pubdate_raw) if pubdate_raw else None


            embed = Embed(
                title=f"**{chaptername}⋆. 𐙚 ˚**",
                url=link,
                description=nameextend or discord.Embed.Empty,
                timestamp=timestamp,
                color=int("A87676", 16),
            )
            embed.set_author(name=f"{translator}˙ᵕ˙")
            if thumb_url:
                embed.set_thumbnail(url=thumb_url)
            embed.set_footer(text=host, icon_url=host_logo)

            # add the button
            coin_label = entry.get("coin","").strip()
            view       = View()
            view.add_item(Button(label=coin_label or "Read here", url=link))

            # send
            await channel.send(content=content, embed=embed, view=view)
            print(f"📨 Sent paid: {chaptername} / {guid}")
            new_last = guid

        # 4) Save the new checkpoint & close
        if new_last and new_last != state.get(FEED_KEY):
            state[FEED_KEY] = new_last
            save_state(state)
            print(f"💾 Updated {STATE_FILE}[\"{FEED_KEY}\"] → {new_last}")

        await bot.close()

    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(send_new_paid_entries())
