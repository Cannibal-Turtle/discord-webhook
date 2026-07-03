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

from message_renderer import render_message, to_discord_api_payload
from git_state_commit import commit_state_update

from novel_mappings import (
    HOSTING_SITE_DATA,
    get_nsfw_novels,
)

# ─── CONFIG ────────────────────────────────────────────────────────────────────
from config_loader import (
    server_channel_id_str,
    TAG_ROLE_MAP,
    get_novel_custom_emoji,
    get_novel_role_url,
    require_file_value,
    require_role_value,
    role_id_to_mention,
    server_value,
)

STATE_PATH = require_file_value("state_path")
BOT_TOKEN  = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = server_channel_id_str("announcements")

GLOBAL_ROLE = role_id_to_mention(require_role_value("new"))
NSFW_ROLE   = role_id_to_mention(require_role_value("nsfw"))

TAG_ROLE_MAP_PATH = require_file_value("tag_role_map_file")
TRANSLATOR_URL = str(server_value("translator_url", "") or "").strip()
# ───────────────────────────────────────────────────────────────────────────────

def get_entry_translator_url(entry) -> str:
    for key in ("translator_url", "translatorUrl", "translatorurl"):
        value = entry.get(key)
        if value:
            return str(value).strip()
    return ""


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

def send_bot_payload(bot_token: str, channel_id: str, message_payload: dict):
    """
    Send rendered TOML payload to Discord via raw API.
    """
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type":  "application/json",
    }

    payload = to_discord_api_payload(message_payload)

    r = requests.post(url, headers=headers, json=payload, timeout=20)
    r.raise_for_status()
    return r


def safe_send_bot_payload(bot_token: str, channel_id: str, message_payload: dict) -> bool:
    """
    Try to send to Discord. If it fails, print and continue without crashing.
    """
    try:
        send_bot_payload(bot_token, channel_id, message_payload)
        return True
    except requests.RequestException as e:
        status = e.response.status_code if e.response else "?"
        body   = e.response.text if e.response else ""
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
  
def normalize_tag(tag: str) -> str:
    """Normalize tags so 'BL', ' bl ', and 'Bl' all match 'bl'."""
    return re.sub(r"\s+", " ", str(tag).strip().casefold())

def build_ping_roles(novel_title: str, tags: list[str] | None = None) -> str:
    """
    Build the ping line that shows on top of the announcement.

    Order:
      1. global @new novels role
      2. tag roles from tag_roles.json
      3. NSFW role last, if applicable
    """
    parts = []

    if GLOBAL_ROLE:
        parts.append(GLOBAL_ROLE.strip())

    if not tags:
        tags = []

    unknown_tags = []

    for tag in tags:
        key = normalize_tag(tag)
        role_id = TAG_ROLE_MAP.get(key)

        if not role_id:
            unknown_tags.append(tag)
            continue

        parts.append(role_id_to_mention(role_id))

    if unknown_tags:
        raise ValueError(
            f"Unknown tag(s) for {novel_title}: {unknown_tags}. "
            f"Add them to {TAG_ROLE_MAP_PATH} or fix the spelling."
        )

    if novel_title in get_nsfw_novels():
        parts.append(NSFW_ROLE)

    # Dedupe while preserving order.
    seen = set()
    clean_parts = []

    for part in parts:
        if not part or part in seen:
            continue

        seen.add(part)
        clean_parts.append(part)

    return " ".join(clean_parts)


def load_novels_from_mapping():
    """
    Flatten HOSTING_SITE_DATA into a list of dicts with the fields we need.
    For launch announcements we ONLY care about novels that actually have a
    free_feed (because you only announce once it's public/free).

    We also pull:
      - translator        (per-novel override, host fallback)
      - host_logo         (host-level)
      - tags              (per novel)     -- resolved through tag_roles.json
      - novel_url, featured_image, custom_emoji, discord_role_url, etc.
    """
    novels = []

    for host_name, host_data in HOSTING_SITE_DATA.items():
        host_logo    = host_data.get("host_logo", "")
        novels_block = host_data.get("novels", {})

        for novel_title, details in novels_block.items():
            free_feed_url = details.get("free_feed")
            if not free_feed_url:
                # we skip novels that aren't publicly readable yet
                continue

            short_code = (details.get("short_code", "") or "").strip().upper()

            novels.append({
                "host":             host_name,
                "translator":       details.get("translator") or host_data.get("translator", ""),
                "translator_url":   details.get("translator_url") or host_data.get("translator_url", ""),
                "host_logo":        host_logo,

                "novel_title":      novel_title,
                "short_code":       short_code,
                "novel_url":        details.get("novel_url", ""),
                "featured_image":   details.get("featured_image", ""),

                "free_feed":        free_feed_url,
                "custom_emoji":     get_novel_custom_emoji(short_code),
                "discord_role_url": get_novel_role_url(short_code),

                "tags": details.get("tags", []),
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

    bot_token  = BOT_TOKEN
    channel_id = CHANNEL_ID
    if not (bot_token and channel_id):
        sys.exit("❌ Missing DISCORD_BOT_TOKEN or config/server.json announcements channel")

    state  = load_state()
    novels = load_novels_from_mapping()

    # current local time (aware) for fallback + footer diff
    now_local = datetime.now(timezone.utc).astimezone()

    for novel in reversed(novels):
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
            chap_field = entry.get("chapter") or ""

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
            # - global launch role
            # - tag roles from tag_roles.json
            # - NSFW role if in get_nsfw_novels
            ping_line = build_ping_roles(
                novel_title=novel_title,
                tags=novel.get("tags", [])
            )
          
            chap_display = chap_field.replace("\u00A0", " ").strip()
            pub_date_iso = chap_dt_local.astimezone(timezone.utc).isoformat()

            ctx = {
                "ping_line": ping_line,
                "title": novel_title,
                "novel_title": novel_title,
                "novel_url": novel.get("novel_url", ""),
                "chapter": chap_display,
                "chapter_link": chap_link,
                "host": host_name,
                "translator": novel.get("translator", ""),
                "translator_url": (
                    get_entry_translator_url(entry)
                    or novel.get("translator_url", "")
                    or TRANSLATOR_URL
                ),
                "description": desc_text,
                "featured_image_url": novel.get("featured_image", ""),
                "host_logo_url": novel.get("host_logo", ""),
                "pub_date_iso": pub_date_iso,
                "short_code": novel.get("short_code", ""),
                "custom_emoji": novel.get("custom_emoji", ""),
                "discord_role_url": novel.get("discord_role_url", ""),
            }

            message_payload = render_message("new_novels", ctx)

            print(
                f"→ Built launch message for {novel_title} "
                f"({len(message_payload.get('content', ''))} chars + "
                f"{len(message_payload.get('embeds', []))} embed)"
            )

            ok = safe_send_bot_payload(
                bot_token=bot_token,
                channel_id=channel_id,
                message_payload=message_payload,
            )

            if ok:
                print(f"✔️ Sent launch announcement for {novel_title}")
                state.setdefault(novel_title, {})["launch_free"] = {
                    "chapter": chap_field,
                    "sent_at": datetime.now().isoformat()
                }
                save_state(state)
                commit_state_update(STATE_PATH)
            else:
                print("→ Send failed; not updating state.json")

            # we only announce once per novel, so break after first match
            break


if __name__ == "__main__":
    main()
