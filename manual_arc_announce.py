#!/usr/bin/env python3
"""
manual_arc_announce.py

One-off announcer for "first arc is paid" scenario.
This will send all 4 Discord messages that process_arc() would send,
using the data for:
- Quick Transmigration: The Villain Is Too Pampered and Alluring
- Arc 1: The Heiress Will Not Be a Cannon Fodder
- No unlocked arcs yet (so unlocked embed will say "None")

Env vars required:
  DISCORD_BOT_TOKEN
  DISCORD_CHANNEL_ID
"""

import os
import requests
import re
import sys


# ─── CONFIG FROM MAPPINGS ────────────────────────────────────────────────────

# Discord auth + channel
BOT_TOKEN  = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = os.environ["DISCORD_CHANNEL_ID"]

# Roles
NOVEL_ROLE     = "<@&1329391480435114005>"      # discord_role_id from mappings
ONGOING_ROLE   = "<@&1329502951764525187>"      # ONGOING_ROLE
NSFW_ROLE      = ""                             # leave "" since this one is SFW
ROLE_COMBINED  = f"{NOVEL_ROLE}{(' | ' + NSFW_ROLE) if NSFW_ROLE else ''}"

# Novel info
NOVEL_TITLE    = "Quick Transmigration: The Villain Is Too Pampered and Alluring"
NOVEL_URL      = "https://dragonholic.com/novel/quick-transmigration-the-villain-is-too-pampered-and-alluring/"
HOST_NAME      = "Dragonholic"
CUSTOM_EMOJI   = "<:emoji_62:1365400946330435654>"
DISCORD_ROLE_URL = "https://discord.com/channels/1329384099609051136/1329419555600203776/1330466188349800458"

# Arc info (simulated first paid arc)
ARC_NUMBER     = 1
ARC_TITLE_BASE = "The Heiress Will Not Be a Cannon Fodder"

# Emoji digits used for "world number" decoration
DIGIT_EMOJI = {
    '0': '<:7987_zero_emj_png:1368137498496335902>',
    '1': '<:5849_one_emj_png:1368137451801149510>',
    '2': '<:4751_two_emj_png:1368137429369753742>',
    '3': '<:5286_three_emj_png:1368137406523637811>',
    '4': '<:4477_four_emj_png:1368137382813106196>',
    '5': '<:3867_five_emj_png:1368137358800715806>',
    '6': '<:8923_six_emj_png:1368137333886550098>',
    '7': '<:4380_seven_emj_png:1368137314240303165>',
    '8': '<:9891_eight_emj_png:1368137290517581995>',
    '9': '<:1898_nine_emj_png:1368137143196717107>',
}


# ─── HELPERS ────────────────────────────────────────────────────────────────

def number_to_emoji(n: int) -> str:
    """Turn 1 -> <:5849_one_emj_png:...>, 24 -> '2''4' emojis, etc."""
    return ''.join(DIGIT_EMOJI[d] for d in str(n))

def format_stored_title(title: str) -> str:
    """
    Given "【Arc 1】The Heiress Will Not Be a Cannon Fodder"
    return "**【Arc 1】**The Heiress Will Not Be a Cannon Fodder"
    """
    m = re.match(r"(【Arc\s+\d+】)\s*(.*)", title)
    if m:
        return f"**{m.group(1)}**{m.group(2)}"
    return f"**{title}**"

def post_message(content=None, embed=None, suppress_previews=False):
    """
    Send a single message to Discord.
    content: string for normal message content
    embed: dict for a single embed, or None
    suppress_previews: if True, send flags=4 (suppress embeds/previews)
    """
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type":  "application/json"
    }

    payload = {
        "allowed_mentions": {"parse": ["roles"]},
    }
    if content is not None:
        payload["content"] = content
    if embed is not None:
        payload["embeds"] = [embed]
    if suppress_previews:
        payload["flags"] = 4  # suppress embeds

    resp = requests.post(url, headers=headers, json=payload)
    if not resp.ok:
        print(f"⚠️ Discord error {resp.status_code}: {resp.text}", file=sys.stderr)
    resp.raise_for_status()
    return True


# ─── BUILD MESSAGE PARTS ────────────────────────────────────────────────────

def build_and_send():
    # world / arc display like the main script
    world_emoji = number_to_emoji(ARC_NUMBER)

    # Build "unlocked" and "locked" lists as if they came from history
    # In this scenario:
    #   unlocked = []  (no free arcs yet)
    #   locked   = ["【Arc 1】The Heiress Will Not Be a Cannon Fodder"]
    unlocked_list = []
    locked_list   = [f"【Arc {ARC_NUMBER}】{ARC_TITLE_BASE}"]

    # (format_stored_title bolds 【Arc n】 part)
    unlocked_md = "\n".join(format_stored_title(t) for t in unlocked_list)
    if unlocked_md.strip() == "":
        unlocked_md = "None"

    locked_lines = [format_stored_title(t) for t in locked_list]

    # Pink arrow marks newest locked arc (last one)
    if locked_lines:
        locked_lines[-1] = (
            "<a:9410pinkarrow:1368139217556996117>"
            + locked_lines[-1]
        )

    locked_md = "\n".join(locked_lines)
    if locked_md.strip() == "":
        locked_md = "None"

    # Header / banner content
    content_header = (
        f"{ROLE_COMBINED} | {ONGOING_ROLE} <a:Crown:1365575414550106154>\n"
        "## <a:announcement:1365566215975731274> NEW ARC ALERT "
        "<a:pinksparkles:1365566023201198161>"
        "<a:Butterfly:1365572264774471700>"
        "<a:pinksparkles:1365566023201198161>\n"
        f"***<:babypinkarrowleft:1365566594503147550>"
        f"<:world_01:1368202193038999562>"
        f"<:world_02:1368202204468613162> {world_emoji}"
        f"<:babypinkarrowright:1365566635838275595>is Live for*** "
        "<a:pinkloading:1365566815736172637>\n"
        f"### [{NOVEL_TITLE}]({NOVEL_URL}) "
        "<a:Turtle_Police:1365223650466205738>\n"
        "❀° ┄───────────────────────╮"
    )

    # Embed 1: unlocked arcs
    embed_unlocked = {
        "description": f"{unlocked_md if unlocked_md == 'None' else '||' + unlocked_md + '||'}",
        "color": 0xFFF9BF  # pale yellow-ish
    }
    # Note: in the real script, unlocked_md isn't spoiler-wrapped.
    # We can mimic exactly: unlocked_md goes in raw, not spoilered.
    # Let's fix that to match the real behavior:
    embed_unlocked["description"] = unlocked_md  # override with raw

    # Embed 2: locked arcs
    embed_locked = {
        "description": f"||{locked_md}||",
        "color": 0xA87676  # brownish/red
    }

    # Footer / CTA message
    footer_and_react = (
        "╰───────────────────────┄ °❀\n"
        f"> *Advance access is ready for you on {HOST_NAME}! "
        "<a:holo_diamond:1365566087277711430>*\n"
        + "<:pinkdiamond_border:1365575603734183936>"
          "<:pinkdiamond_border:1365575603734183936>"
          "<:pinkdiamond_border:1365575603734183936>"
          "<:pinkdiamond_border:1365575603734183936>"
          "<:pinkdiamond_border:1365575603734183936>"
          "<:pinkdiamond_border:1365575603734183936>\n"
        "-# React to the "
        f"{CUSTOM_EMOJI} @ {DISCORD_ROLE_URL} "
        "to get notified on updates and announcements "
        "<a:LoveLetter:1365575475841339435>"
    )

    # Now actually send all 4 messages in order

    print("→ Sending header...")
    post_message(
        content=content_header,
        embed=None,
        suppress_previews=True  # flags: 4
    )

    print("→ Sending unlocked embed...")
    post_message(
        content="<a:5693pinkwings:1368138669004820500> `Unlocked 🔓` <a:5046_bounce_pink:1368138460027813888>",
        embed=embed_unlocked,
        suppress_previews=False
    )

    print("→ Sending locked embed...")
    post_message(
        content="<a:5693pinkwings:1368138669004820500> `Locked 🔐` <a:5046_bounce_pink:1368138460027813888>",
        embed=embed_locked,
        suppress_previews=False
    )

    print("→ Sending footer/react...")
    post_message(
        content=footer_and_react,
        embed=None,
        suppress_previews=True  # flags: 4
    )

    print("✅ Done.")


if __name__ == "__main__":
    build_and_send()
