#!/usr/bin/env python3
"""
new_novel_checker_test.py

Test version of new_novel_checker.py.

Goal:
- Force-send a "New Series Launch" style Discord message for an EXISTING novel,
  even if it's not actually new.
- Send it using your real bot token / channel ID secrets from GitHub.
- Do NOT write to state.json.
- Do NOT care if it's already been "announced".

How this differs from the real script:
- We hard-pick one novel in TARGET_TEST_TITLE.
- We always treat the first matching feed entry as "Chapter 1".
- We skip the "already announced" check.
- We don't update state.json.

So you can preview formatting in your real channel.
"""

import os
import re
import html
import feedparser
import requests
from datetime import datetime, timezone
from novel_mappings import (
    HOSTING_SITE_DATA,
    get_nsfw_novels,
)

# ─── CONFIG ────────────────────────────────────────────────────────────────────

BOT_TOKEN_ENV  = "DISCORD_BOT_TOKEN"
CHANNEL_ID_ENV = "DISCORD_CHANNEL_ID"

GLOBAL_ROLE = "<@&1329502873503006842>"        # @new novels (global ping)
NSFW_ROLE   = "<@&1343352825811439616>"        # @nsfw role ping

# 👇 change this string if you want to test a different title
TARGET_TEST_TITLE = "Quick Transmigration: The Villain Is Too Pampered and Alluring"
# ───────────────────────────────────────────────────────────────────────────────


def parsed_time_to_aware(struct_t, fallback_now):
    if not struct_t:
        return fallback_now
    try:
        aware_utc = datetime(
            struct_t.tm_year,
            struct_t.tm_mon,
            struct_t.tm_mday,
            struct_t.tm_hour,
            struct_t.tm_min,
            struct_t.tm_sec,
            tzinfo=timezone.utc,
        )
        return aware_utc.astimezone()
    except Exception:
        return fallback_now


def nice_footer_time(chap_dt: datetime, now_dt: datetime) -> str:
    chap_day = chap_dt.date()
    now_day  = now_dt.date()
    hhmm     = chap_dt.strftime("%H:%M")

    if chap_day == now_day:
        return f"Today at {hhmm}"

    delta_days = (now_day - chap_day).days
    if delta_days == 1:
        return f"Yesterday at {hhmm}"

    return chap_dt.strftime("%Y-%m-%d %H:%M")


def send_bot_message_embed(bot_token: str, channel_id: str, content: str, embed: dict):
    """
    Send a Discord message containing both a normal text block (`content`)
    and a rich embed (`embed`).
    Uses your bot token to post as the bot to the channel ID.
    """
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type":  "application/json"
    }
    payload = {
        "content": content,
        "embeds": [embed],
        "allowed_mentions": {"parse": ["roles"]},
    }

    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()


def clean_feed_description(raw_html: str) -> str:
    """
    Clean up the <description> block from the feed.

    We:
    - Stop at first <hr> (cut Patreon/Ko-fi calls etc)
    - Strip tags
    - Collapse whitespace
    - Trim to Discord-safe length
    """
    if not raw_html:
        return ""

    parts = re.split(r"(?i)<hr[^>]*>", raw_html, maxsplit=1)
    main_part = parts[0]

    no_tags = re.sub(r"(?s)<[^>]+>", "", main_part)
    text = html.unescape(no_tags)

    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    if len(text) > 4000:
        text = text[:4000].rstrip() + "…"

    return text


def build_ping_roles(novel_title: str,
                     extra_ping_roles_value: str) -> str:
    """
    First line of the announcement.
    Order:
    - GLOBAL_ROLE (@new novels etc.)
    - extra_ping_roles (e.g. @Quick Transmigration @CN dao @Yaoi)
    - NSFW_ROLE at the end *if* this title is in get_nsfw_novels()
    """
    parts = []

    if GLOBAL_ROLE:
        parts.append(GLOBAL_ROLE.strip())

    if extra_ping_roles_value:
        parts.append(extra_ping_roles_value.strip())

    if novel_title in get_nsfw_novels():
        parts.append(NSFW_ROLE)

    return " ".join(p for p in parts if p)


def build_launch_content(ping_line: str,
                         title: str,
                         novel_url: str,
                         chap_name: str,
                         chap_link: str,
                         host: str,
                         role_thread_url: str,
                         custom_emoji: str) -> str:
    """
    The pretty text block above the embed, exactly like production.
    """
    chap_display = chap_name.replace("\u00A0", " ").strip()

    return (
        f"{ping_line} <a:Bow:1365575505171976246>\n"
        "## ꉂ`:fish_cake: ･ﾟ✧ New Series Launch ִֶָ. ..𓂃 ࣪ ִֶָ:wing:་༘࿐<a:1678whalepink:1368136879857205308>\n"
        f"***<a:kikilts_bracket:1365693072138174525>[{title}]({novel_url})<a:lalalts_bracket:1365693058905014313>*** — now officially added to cannibal turtle's lineup! <a:1620cupcakepink:1368136855903801404><a:Stars:1365568624466722816> \n\n"
        f"[{chap_display}]({chap_link}), is out on {host}. "
        "Please give lots of love to our new baby and welcome it to the server "
        "<a:hellokittydance:1365566988826705960>\n"
        "Updates will continue regularly, so hop in early and start reading now <a:2713pandaroll:1368137698212184136> \n"
        f"{'<a:6535_flower_border:1368146360871948321>' * 10}\n"
        f"-# To get pings for new chapters, head to {role_thread_url} "
        f"and react for the role {custom_emoji}"
    )


def build_launch_embed(
    translator: str,
    title: str,
    novel_url: str,
    desc_text: str,
    cover_url: str,
    host_name: str,
    host_logo_url: str,
    chap_dt_local: datetime  # this is the chapter's datetime from the feed
) -> dict:
    """
    Build the embed object:
    - author.name: translator ⋆. 𐙚
    - title/url:   clickable series title
    - description: cleaned summary
    - image.url:   cover art
    - footer:      host name + host logo
    - timestamp:   actual chapter time (Discord will render "Today at HH:MM"
                   in each viewer's local timezone)
    - color:       pastel #AEC6CF
    """

    # Discord expects timestamp in ISO8601, and will auto-localize.
    # We just make sure chap_dt_local is aware (has tzinfo).
    iso_timestamp = chap_dt_local.astimezone(timezone.utc).isoformat()

    embed = {
        "author": {
            "name": f"{translator} ⋆. 𐙚"
        },
        "title": title,
        "url": novel_url,
        "description": desc_text,
        "image": {
            "url": cover_url
        },
        "footer": {
            "text": host_name,
            "icon_url": host_logo_url
        },
        # pastel embed color aec6cf
        "color": 0xAEC6CF,
        # THIS is the magic: send the chapter's time up to Discord
        "timestamp": iso_timestamp,
    }

    return embed


def load_test_novel_from_mapping():
    """
    Pull your HOSTING_SITE_DATA and return just the one novel
    we want to test (TARGET_TEST_TITLE).

    We also pull host info (translator, host_logo, etc.)
    and novel info (featured_image, custom_emoji, etc.)
    which is what the real script uses.
    """
    for host_name, host_data in HOSTING_SITE_DATA.items():
        translator   = host_data.get("translator", "")
        host_logo    = host_data.get("host_logo", "")
        novels_block = host_data.get("novels", {})

        for novel_title, details in novels_block.items():
            if novel_title != TARGET_TEST_TITLE:
                continue

            free_feed_url = details.get("free_feed")
            if not free_feed_url:
                # can't test if there's no free/public feed
                continue

            return {
                "host":             host_name,
                "translator":       translator,
                "host_logo":        host_logo,

                "novel_title":      novel_title,
                "novel_url":        details.get("novel_url", ""),
                "featured_image":   details.get("featured_image", ""),

                "free_feed":        free_feed_url,
                "custom_emoji":     details.get("custom_emoji", ""),
                "discord_role_url": details.get("discord_role_url", ""),

                # like "<@&QuickTransRole> <@&CNdao> <@&Yaoi>"
                "extra_ping_roles": details.get("extra_ping_roles", ""),
            }

    return None


def main():
    bot_token  = os.getenv(BOT_TOKEN_ENV)
    channel_id = os.getenv(CHANNEL_ID_ENV)
    if not (bot_token and channel_id):
        raise SystemExit("❌ Missing DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID (check repo secrets).")

    novel = load_test_novel_from_mapping()
    if not novel:
        raise SystemExit(f"❌ Could not find {TARGET_TEST_TITLE} (or it has no free_feed) in HOSTING_SITE_DATA.")

    host_name   = novel["host"]
    novel_title = novel["novel_title"]
    feed_url    = novel["free_feed"]

    now_local = datetime.now(timezone.utc).astimezone()

    print(f"[test] Fetching free feed for {novel_title} from {feed_url}")
    resp = requests.get(feed_url)
    feed = feedparser.parse(resp.text)
    print(f"[test] Parsed {len(feed.entries)} entries")

    # We'll just grab the FIRST feed item for this novel_title and pretend it's Chapter 1.
    for entry in feed.entries:
        entry_title = (entry.get("title") or "").strip()
        if entry_title != novel_title:
            continue

        # chapter label from feed (could be "Chapter 1180", "Extra 8", whatever)
        chap_field = (
            entry.get("chaptername")
            or entry.get("chapter")
            or ""
        )
        chap_link = entry.link

        # clean summary/description for embed
        raw_desc_html = (
            entry.get("description")
            or entry.get("summary")
            or ""
        )
        desc_text = clean_feed_description(raw_desc_html)

        # timestamp for footer (Today / Yesterday)
        chap_dt_local = parsed_time_to_aware(
            entry.get("published_parsed")
            or entry.get("updated_parsed"),
            now_local
        )

        # build the first line with all the role pings
        ping_line = build_ping_roles(
            novel_title,
            novel.get("extra_ping_roles", "")
        )

        # message text block
        content_msg = build_launch_content(
            ping_line=ping_line,
            title=novel_title,
            novel_url=novel.get("novel_url", ""),
            chap_name=chap_field,
            chap_link=chap_link,
            host=host_name,
            role_thread_url=novel.get("discord_role_url", ""),
            custom_emoji=novel.get("custom_emoji", "")
        )

        # the embed (preview card)
        embed_obj = build_launch_embed(
            translator=novel.get("translator", ""),
            title=novel_title,
            novel_url=novel.get("novel_url", ""),
            desc_text=desc_text,
            cover_url=novel.get("featured_image", ""),
            host_name=host_name,
            host_logo_url=novel.get("host_logo", ""),
            chap_dt_local=chap_dt_local
        )

        print("[test] Sending message to Discord now…")
        send_bot_message_embed(
            bot_token=bot_token,
            channel_id=channel_id,
            content=content_msg,
            embed=embed_obj
        )
        print("[test] Done. Check your channel.")
        return  # stop after first matching entry

    print("❌ No matching entries found in feed.")


if __name__ == "__main__":
    main()
