#!/usr/bin/env python3
import os
import asyncio

import discord
from discord import Embed
from discord.ui import View, Button
from dateutil import parser as dateparser

# ─── CONFIG ───────────────────────────────────────────
TOKEN           = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID      = int(os.getenv("DISCORD_FREE_CHAPTERS_CHANNEL"))
GLOBAL_MENTION  = "<@&1342483851338846288>"
# ───────────────────────────────────────────────────────

if not TOKEN or not CHANNEL_ID:
    raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_FREE_CHAPTERS_CHANNEL must be set")

async def demo_post():
    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        channel = bot.get_channel(CHANNEL_ID)
        if channel is None:
            print(f"❌ Cannot find channel {CHANNEL_ID}")
            await bot.close()
            return

        # — build the text content —
        role_id = "<@&1329391480435114005>"
        content = (
            f"{role_id} | {GLOBAL_MENTION} <a:TurtleDance:1365253970435510293>\n"
            "**Test Chapter 1**  🔓"
        )

        # — build the embed —
        chaptername = "Chapter 1"
        nameextend  = "The very first step"
        link        = "https://example.com/novel/ch1"
        translator  = "DemoTranslator"
        thumb_url   = "https://example.com/cover.jpg"
        host        = "ExampleHost"
        host_logo   = "https://example.com/logo.png"
        pubdate_raw = "2025-04-25T12:00:00+00:00"
        timestamp   = dateparser.parse(pubdate_raw)

        embed = Embed(
            title=f"**{chaptername}**⋆. 𐙚 ˚",
            url=link,
            description=nameextend,
            timestamp=timestamp,
            color=int("FFF9BF", 16),
        )
        embed.set_author(name=f"{translator}˙ᵕ˙")
        embed.set_thumbnail(url=thumb_url)
        embed.set_footer(text=host, icon_url=host_logo)

        # — attach a “Read here” button —
        view = View()
        view.add_item(Button(label="Read here", url=link))

        # — send it!
        await channel.send(content=content, embed=embed, view=view)
        print("📨 Demo free-chapter alert sent")
        await bot.close()

    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(demo_post())
