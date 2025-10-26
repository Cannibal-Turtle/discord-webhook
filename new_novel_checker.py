#!/usr/bin/env python3
"""
new_novel_checker.py

Announce a brand new novel when it FIRST becomes available for free/public reading.

Usage:
  python new_novel_checker.py --feed free

Behavior:
- For each novel in HOSTING_SITE_DATA that has a free_feed:
    - Parse the free feed (RSS).
    - Find an entry for that novel whose chapter looks like the first drop:
        "Chapter 1", "Ch 1", "Prologue", or "1.1".
    - If we haven't announced this novel before:
        - Build a launch message (with your sparkle text + role pings).
        - Build an embed (translator, clickable title, cleaned description,
          cover image, footer with host + timestamp).
        - Post both to Discord.
        - Write launch_free info into state.json so we never post it again.

Env vars required:
  DISCORD_BOT_TOKEN  -> your bot token (not webhook)
  DISCORD_CHANNEL_ID -> channel ID to post in
"""

import argparse
import json
import os
import sys
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

STATE_PATH     = "state.json"
BOT_TOKEN_ENV  = "DISCORD_BOT_TOKEN"
CHANNEL_ID_ENV = "DISCORD_CHANNEL_ID"

GLOBAL_ROLE = "<@&1329502873503006842>"
NSFW_ROLE = "<@&1343352825811439616>"

# ───────────────────────────────────────────────────────────────────────────────


def load_state(path=STATE_PATH):
    """Load state.json so we know what we've already announced."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(state, path=STATE_PATH):
    """Persist state.json back to disk."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def parsed_time_to_aware(struct_t, fallback_now):
    """
    Convert a feedparser time.struct_time into an aware datetime
    (assume UTC from feed, then localize).
    If missing or bad, return fallback_now.
    """
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
    """
    Match your style:
    "Today at HH:MM"
    "Yesterday at HH:MM"
    or "YYYY-MM-DD HH:MM"
    """
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
    We allow role mentions by specifying allowed_mentions.parse=["roles"].
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


def safe_send_bot_embed(bot_token: str, channel_id: str, content: str, embed: dict):
    """
    Try to send to Discord. If it fails, just print and continue without crashing.
    """
    try:
        send_bot_message_embed(bot_token, channel_id, content, embed)
        return True
    except requests.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        body   = e.response.text       if e.response else ""
        print(f"⚠️ Bot send failed ({status}):\n{body}", file=sys.stderr)
        return False


def is_first_chapter_name(chapter_field: str) -> bool:
    """
    Decide if a chapter title means "this is the first public drop".
    We match:
      - "Chapter 1", "Ch 1", "Chapter 001", "Ch.01"
      - "Episode 1", "Ep 1", "Ep.01"
      - "Prologue"
      - "1.1" (or "1 .1", "1. 1", "1．1"), but not "2.1", "10.1", etc.
    """
    if not chapter_field:
        return False

    text = chapter_field.lower().strip()

    # ch 1 / chapter 1 / chapter 001 / ch.01
    if re.search(r"\bch(?:apter)?\.?\s*0*1\b", text):
        return True

    # ep 1 / episode 1 / ep.01
    if re.search(r"\bep(?:isode)?\.?\s*0*1\b", text):
        return True

    # prologue
    if "prologue" in text:
        return True

    # 1.1-ish (arc 1 part 1)
    # \b1[．\.]\s*0*1\b  matches "1.1", "1．1", "1.01"
    # but won't match "21.1" or "10.1" because of the word boundary before the 1.
    if re.search(r"\b1[．\.]\s*0*1\b", text):
        return True

    return False


def clean_feed_description(raw_html: str) -> str:
    """
    Take the <description><![CDATA[ ... ]]> from the feed entry and
    turn it into clean text for the embed.

    Steps:
    - Cut off everything after the first <hr> (case-insensitive),
      because after that is usually Ko-fi / NU promo / server links.
    - Strip all remaining HTML tags.
    - HTML-unescape entities (&nbsp;, &quot;, etc).
    - Squash extra whitespace.
    - Truncate to ~4000 chars (Discord embed.description must be <=4096).
    """
    if not raw_html:
        return ""

    # 1) Stop at the first <hr ...>
    parts = re.split(r"(?i)<hr[^>]*>", raw_html, maxsplit=1)
    main_part = parts[0]

    # 2) Remove all tags
    no_tags = re.sub(r"(?s)<[^>]+>", "", main_part)

    # 3) Unescape HTML entities
    text = html.unescape(no_tags)

    # 4) Normalize whitespace
    # strip leading/trailing spaces on lines, collapse multi-spaces
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    # 5) Truncate if huge
    if len(text) > 4000:
        text = text[:4000].rstrip() + "…"

    return text


def build_ping_roles(novel_title: str,
                     extra_ping_roles_value: str) -> str:
    """
    Build the ping line that shows on top of the announcement.

    Desired final shape:
      @new novels @Quick Transmigration @CN dao @Yaoi [@NSFW if needed]

    We do:
    - GLOBAL_ROLE first (that's your global "@new novels" role)
    - then extra_ping_roles (which you already set in mapping per novel,
      e.g. "@Quick Transmigration @CN dao @Yaoi")
    - then, IF the novel title is in get_nsfw_novels(), append NSFW_ROLE
      at the very end

    Order matters because you explicitly want NSFW last.
    """
    parts = []

    # 1. global ping role for all new launches
    if GLOBAL_ROLE:
        parts.append(GLOBAL_ROLE.strip())

    # 2. all per-novel + genre roles in the exact order you wrote them
    if extra_ping_roles_value:
        parts.append(extra_ping_roles_value.strip())

    # 3. if this novel is NSFW, tack on the NSFW role at the end
    if novel_title in get_nsfw_novels():
        parts.append(NSFW_ROLE)

    # Join with spaces
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
    Build the normal text content (outside the embed).
    Matches your style:

    @new novels @CN dao @Quick Transmigration @Yaoi
    ## ꉂ`:fish_cake: ...
    ***『[Title](novel_url)』*** — now officially ...
    [Chapter 1](chap_link), is out on Host. ...
    ✎﹏...
    -# To get pings...
    """
    # normalize NBSP etc.
    chap_display = chap_name.replace("\u00A0", " ").strip()

    # inline emojis exactly as text (no constants)
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


def shorten_description(desc_text: str, max_words: int = 50) -> str:
    """
    Keep only the first `max_words` words of desc_text.
    If truncated, add "...".
    """
    if not desc_text:
        return ""

    words = desc_text.split()
    if len(words) <= max_words:
        return desc_text

    preview = " ".join(words[:max_words])
    return preview.rstrip() + "..."


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


def load_novels_from_mapping():
    """
    Flatten HOSTING_SITE_DATA into a list of dicts with the fields we need.
    For launch announcements we ONLY care about novels that actually have a
    free_feed (because you only announce once it's public/free).

    We also pull:
      - translator        (host-level)
      - host_logo         (host-level)
      - discord_role_id   (per novel)     -- used by get_novel_discord_role()
      - extra_ping_roles  (per novel)     -- NEW: for @CN dao @Yaoi etc
      - novel_url, featured_image, custom_emoji, discord_role_url, etc.
    """
    novels = []

    for host_name, host_data in HOSTING_SITE_DATA.items():
        translator   = host_data.get("translator", "")
        host_logo    = host_data.get("host_logo", "")
        novels_block = host_data.get("novels", {})

        for novel_title, details in novels_block.items():
            free_feed_url = details.get("free_feed")
            if not free_feed_url:
                # we skip novels that aren't publicly readable yet
                continue

            novels.append({
                "host":             host_name,
                "translator":       translator,
                "host_logo":        host_logo,

                "novel_title":      novel_title,
                "novel_url":        details.get("novel_url", ""),
                "featured_image":   details.get("featured_image", ""),

                "free_feed":        free_feed_url,
                "custom_emoji":     details.get("custom_emoji", ""),
                "discord_role_url": details.get("discord_role_url", ""),

                # optional: per-novel bundle like "@CN dao @Yaoi"
                "extra_ping_roles": details.get("extra_ping_roles", ""),
            })

    return novels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--feed",
        choices=["free"],
        required=True,
        help="We only announce once free/public chapters are available."
    )
    args = parser.parse_args()

    bot_token  = os.getenv(BOT_TOKEN_ENV)
    channel_id = os.getenv(CHANNEL_ID_ENV)
    if not (bot_token and channel_id):
        sys.exit("❌ Missing DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID")

    state  = load_state()
    novels = load_novels_from_mapping()

    # current local time (aware) for fallback + footer diff
    now_local = datetime.now(timezone.utc).astimezone()

    for novel in novels:
        novel_title = novel["novel_title"]
        host_name   = novel["host"]

        # have we already launched this novel?
        if state.get(novel_title, {}).get("launch_free"):
            print(f"→ skipping {novel_title} (launch_free) — already launched")
            continue

        feed_url = novel.get("free_feed")
        if not feed_url:
            continue  # shouldn't happen because we filtered

        print(f"Fetching free feed for {novel_title} from {feed_url}")
        resp = requests.get(feed_url)
        feed = feedparser.parse(resp.text)
        print(
            f"Parsed {len(feed.entries)} entries "
            f"(Content-Type: {resp.headers.get('Content-Type')})"
        )

        # scan feed entries for "first chapter" of THIS novel
        for entry in feed.entries:
            entry_title = (entry.get("title") or "").strip()

            # Make sure this entry is actually for THIS novel.
            # Your feed uses <title> as the novel title for each item.
            if entry_title != novel_title:
                continue

            # Chapter name (e.g. "Chapter 1", "Prologue", "1.1")
            chap_field = (
                entry.get("chaptername")
                or entry.get("chapter")
                or ""
            )
            if not is_first_chapter_name(chap_field):
                continue

            # Link to this first public chapter
            chap_link = entry.link

            # <description> contains the blurb/summary block; clean it
            raw_desc_html = (
                entry.get("description")
                or entry.get("summary")
                or ""
            )
            desc_text = clean_feed_description(raw_desc_html)

            # Timestamps for the embed footer
            chap_dt_local = parsed_time_to_aware(
                entry.get("published_parsed")
                or entry.get("updated_parsed"),
                now_local
            )

            # Build ping roles line:
            # - global launch role(s)
            # - novel role (+ nsfw if in get_nsfw_novels)
            # - any per-novel extra pings (like @CN dao, @Yaoi)
            ping_line = build_ping_roles(
                novel_title,
                novel.get("extra_ping_roles", "")
            )

            # Build user-facing text content
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

            # Build embed object
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

            print(
                f"→ Built launch message for {novel_title} "
                f"({len(content_msg)} chars content + 1 embed)"
            )

            # Send to Discord
            ok = safe_send_bot_embed(
                bot_token=bot_token,
                channel_id=channel_id,
                content=content_msg,
                embed=embed_obj
            )

            if ok:
                print(f"✔️ Sent launch announcement for {novel_title}")
                state.setdefault(novel_title, {})["launch_free"] = {
                    "chapter": chap_field,
                    "sent_at": datetime.now().isoformat()
                }
                save_state(state)
            else:
                print("→ Send failed; not updating state.json")

            # we only announce once per novel, so break after first match
            break


if __name__ == "__main__":
    main()
