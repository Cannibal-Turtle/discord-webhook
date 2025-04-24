import os
import json
import asyncio
import feedparser
from dateutil import parser as dateparser

import discord
from discord import Embed

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN       = os.environ["DISCORD_BOT_TOKEN"]s
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
    state   = load_state()
    print("🔍 Loaded state:", state)

    feed    = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))
    print(f"🔍 Parsed feed, {len(entries)} total entries")

    # 1) Compute only-new slice
    guids   = [(e.get("guid") or e.get("id")) for e in entries]
    last    = state.get("last_guid")
    to_send = entries[guids.index(last)+1:] if last in guids else entries
    print(f"🔍 {len(to_send)} new comments to send")

    # 2) Early exit if nothing to send
    if not to_send:
        print("🛑 No new comments—skipping Discord login.")
        return

    print("🔌 Connecting to Discord…")
    intents = discord.Intents.default()
    bot     = discord.Client(intents=intents)

    new_last = last  # scoped for final save

    @bot.event
    async def on_ready():
        nonlocal new_last
        print("✅ on_ready fired")
        channel = bot.get_channel(CHANNEL_ID)
        print(f"🔎 Channel object: {channel!r}")
        if channel is None:
            print(f"❌ Cannot find channel {CHANNEL_ID}")
            await bot.close()
            return

        for entry in to_send:
            guid        = entry.get("guid") or entry.get("id")
            print(f"✉️ Preparing to send comment {guid}")
            title       = entry.get("title", "").strip()
            role_id     = entry.get("discord_role_id", "").strip()
            content     = f"New comment for **{title}** || {role_id}"

            author      = entry.get("author") or entry.get("dc_creator", "")
            chapter     = entry.get("chapter", "").strip()
            comment_txt = entry.get("description", "").strip()
            reply_chain = entry.get("reply_chain", "").strip()
            host        = entry.get("host", "").strip()
            host_logo   = (entry.get("hostLogo") or entry.get("hostlogo") or {}).get("url", "")

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

            # ← Wrap send in a timeout so it errors fast if there's an issue
            try:
                print("⏳ Awaiting channel.send…")
                await asyncio.wait_for(channel.send(content=content, embed=embed), timeout=15)
                print(f"✅ Successfully sent comment {guid}")
                new_last = guid
            except Exception as e:
                print(f"❗ Error sending comment {guid}:", repr(e))
                # optionally continue or break here

        print("👋 Finished loop, closing client")
        await bot.close()

    try:
        # give the gateway up to 60s to connect, then timeout
        await asyncio.wait_for(bot.start(TOKEN), timeout=60)
        print("🛑 bot.start() returned normally")
    except asyncio.TimeoutError:
        print("⌛ bot.start() timed out after 60s")
    except Exception as e:
        print("❗ Exception in bot.start():", repr(e))
    finally:
        # 3) Save state regardless
        if new_last and new_last != state.get("last_guid"):
            state["last_guid"] = new_last
            save_state(state)
            print(f"💾 Updated comments state.last_guid → {new_last}")

if __name__ == "__main__":
    asyncio.run(send_new_comments())
