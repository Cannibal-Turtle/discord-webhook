#!/usr/bin/env python3
"""
new_arc_checker_test.py

Goal:
- Preview the "NEW ARC ALERT" multi-message announcement format.
- Do NOT modify history.json.
- Do NOT commit or push.
- Optionally send to Discord so you can eyeball formatting.

How it works:
- We pick TARGET_TEST_TITLE.
- We load that novel from HOSTING_SITE_DATA.
- We load its history_file (unlocked / locked arcs).
- We pick the latest locked arc (or fake one if none).
- We build the 4 Discord messages exactly like production:
    1) header banner
    2) unlocked embed
    3) locked embed
    4) footer/react line
- If DRY_RUN=true: just print them.
- Else: actually POST them to your channel with your bot token.

We DO NOT update last_announced, and we DO NOT write history back.
"""

import os
import json
import re
import sys
import requests
from novel_mappings import HOSTING_SITE_DATA, get_nsfw_novels

# ─── CONFIG ──────────────────────────────────────────────────────────

BOT_TOKEN_ENV   = "DISCORD_BOT_TOKEN"
CHANNEL_ID_ENV  = "DISCORD_CHANNEL_ID"

ONGOING_ROLE    = "<@&1329502951764525187>"
NSFW_ROLE_ID    = "<@&1343352825811439616>"

# pick which series you want to preview
TARGET_TEST_TITLE = "Quick Transmigration: The Villain Is Too Pampered and Alluring"

# set DRY_RUN=true in GitHub Actions to avoid actually hitting Discord
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# ─── DIGIT → EMOJI MAP (for the arc number ribbon) ───────────────────

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

def number_to_emoji(n: int) -> str:
    """24 -> emoji('2') + emoji('4')."""
    return ''.join(DIGIT_EMOJI[d] for d in str(n))


# ─── SMALL HELPERS (mirrors prod new_arc_checker.py) ──────────────────

def deduplicate(lst):
    """dedupe but keep order."""
    seen = set()
    out = []
    for x in lst:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def extract_arc_number(title):
    """
    "【Arc 12】Some Arc Name" -> 12
    returns None if not matched
    """
    m = re.search(r"【Arc\s*(\d+)】", title)
    return int(m.group(1)) if m else None

def format_stored_title(title):
    """
    Turns "【Arc 7】Cute Arc" into "**【Arc 7】**Cute Arc"
    for the embed body.
    """
    m = re.match(r"(【Arc\s+\d+】)\s*(.*)", title)
    if m:
        return f"**{m.group(1)}**{m.group(2)}"
    return f"**{title}**"


# ─── LOAD NOVEL + HISTORY ─────────────────────────────────────────────

def load_test_novel_from_mapping():
    """
    Look through HOSTING_SITE_DATA and grab the block for TARGET_TEST_TITLE.
    We pull:
    - host (ex: "Dragonholic")
    - discord role mention
    - novel_url
    - custom_emoji
    - discord_role_url
    - history_file (path in repo)
    """
    for host_name, host_data in HOSTING_SITE_DATA.items():
        novels_block = host_data.get("novels", {})
        for novel_title, details in novels_block.items():
            if novel_title != TARGET_TEST_TITLE:
                continue

            return {
                "host":             host_name,
                "novel_title":      novel_title,
                "role_mention":     details.get("discord_role_id", ""),
                "novel_link":       details.get("novel_url", ""),
                "custom_emoji":     details.get("custom_emoji", ""),
                "discord_role_url": details.get("discord_role_url", ""),
                "history_file":     details.get("history_file", ""),
            }
    return None


def load_history_safely(history_file):
    """
    Load the history json for this novel WITHOUT mutating it.
    If file is missing, fake a minimal structure.
    """
    if not history_file:
        print("❌ This novel has no history_file in mapping.")
        return {"unlocked": [], "locked": [], "last_announced": ""}

    try:
        with open(history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("unlocked", [])
        data.setdefault("locked", [])
        data.setdefault("last_announced", "")
        print(f"📂 loaded {history_file}: "
              f"{len(data['unlocked'])} unlocked / {len(data['locked'])} locked "
              f"(last_announced={data['last_announced']})")
        return data
    except FileNotFoundError:
        print(f"⚠️ history file {history_file} not found; faking.")
        return {"unlocked": [], "locked": [], "last_announced": ""}


# ─── SENDING OR PRINTING ─────────────────────────────────────────────

def send_discord_message(bot_token, channel_id, content=None, embed=None):
    """
    Minimal sender. Honors DRY_RUN.
    - content: string
    - embed: dict (Discord embed object) or None
    """
    if DRY_RUN:
        print("🧪 DRY_RUN would send:")
        if content:
            print("CONTENT >>>")
            print(content)
            print("<<< END CONTENT")
        if embed:
            print("EMBED >>>")
            print(json.dumps(embed, indent=2, ensure_ascii=False))
            print("<<< END EMBED")
        print("────────────────────────────")
        return True  # pretend success

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type":  "application/json"
    }
    payload = {
        "allowed_mentions": {"parse": ["roles"]},
    }
    if content is not None:
        payload["content"] = content
        # we like suppress-embeds style (flags:4) for plain lines like header/footer
        # only set flags if there's NO rich embed, same as prod header/footer behavior
        if embed is None:
            payload["flags"] = 4

    if embed is not None:
        payload["embeds"] = [embed]

    r = requests.post(url, headers=headers, json=payload)
    if not r.ok:
        print(f"⚠️ Discord error {r.status_code}: {r.text}", file=sys.stderr)
    r.raise_for_status()
    return True


# ─── MAIN BUILD LOGIC ────────────────────────────────────────────────

def main():
    # env
    bot_token  = os.getenv(BOT_TOKEN_ENV)
    channel_id = os.getenv(CHANNEL_ID_ENV)

    if not DRY_RUN:
        # if we actually want to send to Discord, we need creds
        if not bot_token or not channel_id:
            sys.exit("❌ Missing DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID")
    else:
        print("🧪 DRY_RUN mode active (no Discord send, no file writes)")

    # pick the novel
    novel = load_test_novel_from_mapping()
    if not novel:
        sys.exit(f"❌ Could not find {TARGET_TEST_TITLE} in HOSTING_SITE_DATA")

    # is it NSFW?
    is_nsfw = novel["novel_title"] in get_nsfw_novels()
    base_mention = novel["role_mention"] + (f" | {NSFW_ROLE_ID}" if is_nsfw else "")

    # load current arc history
    history = load_history_safely(novel["history_file"])

    # figure out which arc we're "announcing"
    locked_list = list(history.get("locked", []))
    if locked_list:
        newest_locked_full = locked_list[-1]
    else:
        # if no locked arcs exist yet, fake one so you can still preview styling
        newest_locked_full = "【Arc 1】Preview Arc Name"
        locked_list = [newest_locked_full]

    # build pretty arc number ribbon
    world_number = extract_arc_number(newest_locked_full)
    world_emoji = number_to_emoji(world_number) if world_number is not None else ""

    # unlocked list text
    unlocked_md = "\n".join(format_stored_title(t) for t in history.get("unlocked", []))

    # locked list text
    locked_lines = [format_stored_title(t) for t in locked_list]
    locked_lines = deduplicate(locked_lines)
    if locked_lines:
        # mark newest as active using your pink arrow
        locked_lines[-1] = (
            "<a:9410pinkarrow:1368139217556996117>" + locked_lines[-1]
        )
    locked_md = "\n".join(locked_lines)

    # build the 4 messages exactly like prod new_arc_checker.py:

    # 1) header banner message
    content_header = (
        f"{base_mention} | {ONGOING_ROLE} <a:Crown:1365575414550106154>\n"
        "## <a:announcement:1365566215975731274> NEW ARC ALERT "
        "<a:pinksparkles:1365566023201198161>"
        "<a:Butterfly:1365572264774471700>"
        "<a:pinksparkles:1365566023201198161>\n"
        f"***<:babypinkarrowleft:1365566594503147550>"
        f"<:world_01:1368202193038999562>"
        f"<:world_02:1368202204468613162> {world_emoji}"
        f"<:babypinkarrowright:1365566635838275595>is Live for*** "
        "<a:pinkloading:1365566815736172637>\n"
        f"### [{novel['novel_title']}]({novel['novel_link']}) "
        "<a:Turtle_Police:1365223650466205738>\n"
        "❀° ┄───────────────────────╮"
    )

    # 2) unlocked embed
    embed_unlocked = {
        "description": f"||{unlocked_md}||" if unlocked_md else "None",
        "color": 0xFFF9BF
    }

    # 3) locked embed
    embed_locked = {
        "description": f"||{locked_md}||" if locked_md else "None",
        "color": 0xA87676
    }

    # 4) footer / react line
    footer_and_react = (
        "╰───────────────────────┄ °❀\n"
        f"> *Advance access is ready for you on {novel['host']}! "
        "<a:holo_diamond:1365566087277711430>*\n"
        + "<:pinkdiamond_border:1365575603734183936>" * 6
        + "\n-# React to the "
        + f"{novel['custom_emoji']} @ {novel['discord_role_url']} "
        + "to get notified on updates and announcements "
        "<a:LoveLetter:1365575475841339435>"
    )

    # actually send (or just print if DRY_RUN)
    ok1 = send_discord_message(
        bot_token, channel_id,
        content=content_header,
        embed=None
    )

    ok2 = send_discord_message(
        bot_token, channel_id,
        content="<a:5693pinkwings:1368138669004820500> `Unlocked 🔓` <a:5046_bounce_pink:1368138460027813888>",
        embed=embed_unlocked
    )

    ok3 = send_discord_message(
        bot_token, channel_id,
        content="<a:5693pinkwings:1368138669004820500> `Locked 🔐` <a:5046_bounce_pink:1368138460027813888>",
        embed=embed_locked
    )

    ok4 = send_discord_message(
        bot_token, channel_id,
        content=footer_and_react,
        embed=None
    )

    if ok1 and ok2 and ok3 and ok4:
        print("✅ Test arc alert built successfully.")
    else:
        print("⚠️ At least one send/print failed.", file=sys.stderr)


if __name__ == "__main__":
    main()
