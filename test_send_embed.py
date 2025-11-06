# test_send_embed.py
import os
import argparse
import asyncio
from io import BytesIO

import aiohttp
import discord
from discord import Embed

"""
Usage examples:

# normal (no blur), remote thumbnail
DISCORD_BOT_TOKEN=xxx python test_send_embed.py \
  --channel 1330049962129489930 \
  --title "Test Chapter" \
  --desc "Just a test." \
  --thumb "https://i.imgur.com/yourimage.jpg" \
  --ping "<@&1342483851338846288>"

# NSFW blur (spoiler), attach image so it’s blurred
DISCORD_BOT_TOKEN=xxx python test_send_embed.py \
  --channel 1330049962129489930 \
  --title "NSFW Test" \
  --desc "Spoiler-blurred thumb" \
  --thumb "https://i.imgur.com/yourimage.jpg" \
  --nsfw 1 \
  --ping "<@&1342483851338846288> <@&1343352825811439616>"
"""

def allowed_mentions_roles_only():
    return discord.AllowedMentions(everyone=False, users=False, roles=True)

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", type=int, required=True)
    ap.add_argument("--title", default="Test Title")
    ap.add_argument("--desc", default="Test description")
    ap.add_argument("--url", default="https://example.com")
    ap.add_argument("--thumb", default="")           # image URL to test
    ap.add_argument("--nsfw", type=int, default=0)   # 1 = blur via spoiler
    ap.add_argument("--ping", default="")            # role mentions to include in content
    ap.add_argument("--use-image", action="store_true", help="Use image slot instead of thumbnail")
    args = ap.parse_args()

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("Missing DISCORD_BOT_TOKEN")

    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        ch = bot.get_channel(args.channel)
        if not ch:
            print(f"Cannot find channel {args.channel}")
            await bot.close()
            return

        embed = Embed(title=args.title, url=args.url, description=args.desc, color=0xFFF9BF)

        files = None
        # If nsfw=1 and thumb provided: download and attach as SPOILER_… so Discord blurs it
        if args.nsfw and args.thumb:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(args.thumb, timeout=20) as r:
                    if r.status == 200:
                        data = await r.read()
                        fname = "SPOILER_test.jpg"
                        files = [discord.File(BytesIO(data), filename=fname)]
                        attach_url = f"attachment://{fname}"
                        if args.use_image:
                            embed.set_image(url=attach_url)
                        else:
                            embed.set_thumbnail(url=attach_url)
                    else:
                        # fallback to remote URL if download failed
                        if args.use_image:
                            embed.set_image(url=args.thumb)
                        else:
                            embed.set_thumbnail(url=args.thumb)
        else:
            # non-nsfw or no image download needed: point to remote URL directly
            if args.thumb:
                if args.use_image:
                    embed.set_image(url=args.thumb)
                else:
                    embed.set_thumbnail(url=args.thumb)

        content = args.ping.strip() if args.ping else ""

        await ch.send(
            content=content,
            embed=embed,
            files=files or None,
            allowed_mentions=allowed_mentions_roles_only(),
        )
        print("✅ Sent test message")
        await bot.close()

    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
