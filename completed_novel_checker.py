#!/usr/bin/env python3
"""
completed_novel_checker.py

Run this via your repository_dispatch (or on-demand) whenever your feeds are regenerated.

It will fire:
- a “paid completion” announcement when the paid_feed hits last_chapter,
  and mark state[novel]["paid_completion"].
- a “free completion” announcement when the free_feed (for series that ALSO had paid)
  hits last_chapter, and mark state[novel]["free_completion"].
- an “only_free completion” announcement (for series that ONLY have free_feed and no paid_feed),
  and mark state[novel]["only_free_completion"].

Usage:
  python completed_novel_checker.py --feed paid
  python completed_novel_checker.py --feed free
"""

import argparse
import json
import os
import sys
import feedparser
import requests
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
from novel_mappings import HOSTING_SITE_DATA, get_nsfw_novels
from message_renderer import render_message, to_discord_api_payload

# ─── CONFIG ────────────────────────────────────────────────────────────────────
from config_loader import (
    get_novel_role_id,
    get_novel_role_url,
    require_file_value,
    require_role_value,
    role_id_to_mention,
)

STATE_PATH     = require_file_value("state_path")
BOT_TOKEN_ENV  = "DISCORD_BOT_TOKEN"
CHANNEL_ID_ENV = "DISCORD_CHANNEL_ID"

COMPLETE_ROLE = role_id_to_mention(require_role_value("complete"))
NSFW_ROLE     = role_id_to_mention(require_role_value("nsfw"))
# ────────────────────────────────────────────────────────────────────────────────


def get_series_role_from_short_code(short_code: str) -> str:
    short_code = (short_code or "").strip().upper()
    role_id = get_novel_role_id(short_code)
    return role_id_to_mention(role_id)

def load_state(path=STATE_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(state, path=STATE_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def send_bot_message(bot_token: str, channel_id: str, content: str):
    """
    Post the same `content` via your bot account to `channel_id`.
    """
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type":  "application/json"
    }
    payload = {
        "content": content,
        "allowed_mentions": {"parse": ["roles"]},
        "flags": 4  # suppress embeds for cleaner wall text
    }
    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()


def safe_send_bot(bot_token: str, channel_id: str, content: str):
    """
    Try sending via bot, but catch HTTP errors so the rest of the script continues.
    """
    try:
        send_bot_message(bot_token, channel_id, content)
        return True
    except requests.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        body   = e.response.text       if e.response else ""
        print(f"⚠️ Bot send failed ({status}):\n{body}", file=sys.stderr)
        return False


def get_duration(start_date_str: str, end_date: datetime) -> str:
    """
    Converts a start date (DD/MM/YYYY) to a human-readable duration vs end_date.
    Returns "" if no valid start_date_str was provided.
    """
    if not start_date_str:
        return ""

    try:
        day, month, year = map(int, start_date_str.split("/"))
        start = datetime(year, month, day)
    except Exception:
        # invalid format → give up on duration entirely
        return ""

    delta = relativedelta(end_date, start)

    years = delta.years
    months = delta.months
    days = delta.days

    if years > 0:
        if months > 0:
            return (
                f"{'a' if years == 1 else years} year{'s' if years > 1 else ''} "
                f"and {'a' if months == 1 else months} month{'s' if months > 1 else ''}"
            )
        return f"{'a' if years == 1 else years} year{'s' if years > 1 else ''}"

    if months > 0:
        return f"{'a' if months == 1 else months} month{'s' if months > 1 else ''}"

    weeks = days // 7
    remaining_days = days % 7

    if weeks > 0:
        return f"{weeks} week{'s' if weeks != 1 else ''}"

    if remaining_days > 0:
        return "more than a week"

    return "less than a week"

def join_role_mentions(*parts):
    """
    Join role strings that may already contain '|' or spaces, deduping in order.
    Output uses ' | ' as your house style here.
    """
    seen, out = set(), []
    for p in parts:
        if not p:
            continue
        # split on pipes or spaces so bundles like "A | B C" are handled
        for seg in (x.strip() for x in re.split(r"[| ]+", p) if x.strip()):
            if seg not in seen:
                seen.add(seg)
                out.append(seg)
    return " | ".join(out)

def build_completion_mention(novel: dict) -> str:
    """
    Compose: <novel role> [ + NSFW if needed ] + COMPLETE_ROLE
    NSFW is appended last, mirroring new_novel_checker’s visual.
    """
    base_role = (novel.get("role_mention") or "").strip()
    nsfw_tail = NSFW_ROLE if novel.get("novel_title") in get_nsfw_novels() else None
    # COMPLETE_ROLE goes in the same line, deduped
    return join_role_mentions(base_role, COMPLETE_ROLE, nsfw_tail)


def build_completion_context(novel, chap_field, chap_link, duration: str = "") -> dict:
    return {
        "completion_mention": build_completion_mention(novel),
        "novel_title": novel.get("novel_title", ""),
        "novel_link": novel.get("novel_link", ""),
        "host": novel.get("host", ""),
        "discord_role_url": novel.get("discord_role_url", ""),
        "chapter_count": novel.get("chapter_count", "the entire series"),
        "chapter_text": (chap_field or "").replace("\u00A0", " "),
        "chapter_link": chap_link,
        "duration": duration,
    }


def build_paid_completion(novel, chap_field, chap_link, duration: str):
    variant = "paid_with_duration" if duration else "paid_no_duration"
    ctx = build_completion_context(novel, chap_field, chap_link, duration)
    return render_message("completed_novels", ctx, variant=variant)


def build_free_completion(novel, chap_field, chap_link):
    ctx = build_completion_context(novel, chap_field, chap_link)
    return render_message("completed_novels", ctx, variant="free")


def build_only_free_completion(novel, chap_field, chap_link, duration: str):
    variant = "only_free_with_duration" if duration else "only_free_no_duration"
    ctx = build_completion_context(novel, chap_field, chap_link, duration)
    return render_message("completed_novels", ctx, variant=variant)
  

def load_novels():
    """
    Pull novels directly from HOSTING_SITE_DATA.
    Only include novels that:
    - define last_chapter (so we know what "final" means)
    - and have at least one feed (free or paid)
    """
    novels = []
    for host, host_data in HOSTING_SITE_DATA.items():
        for title, details in host_data.get("novels", {}).items():
            last = details.get("last_chapter")
            if not last:
                continue

            free = details.get("free_feed")
            paid = details.get("paid_feed")
            if not (free or paid):
                continue

            short_code = (details.get("short_code", "") or "").strip().upper()

            novels.append({
                "novel_title":      title,
                "short_code":       short_code,
                "role_mention":     get_series_role_from_short_code(short_code),
                "host":             host,
                "novel_link":       details.get("novel_url", ""),
                "chapter_count":    details.get("chapter_count", ""),
                "last_chapter":     last,
                "start_date":       details.get("start_date", ""),
                "free_feed":        free,
                "paid_feed":        paid,
                "discord_role_url": get_novel_role_url(short_code),
            })
    return novels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", choices=["paid", "free"], required=True)
    args = parser.parse_args()

    bot_token  = os.getenv(BOT_TOKEN_ENV)
    channel_id = os.getenv(CHANNEL_ID_ENV)
    if not (bot_token and channel_id):
        sys.exit("❌ Missing DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID")

    state  = load_state()
    novels = load_novels()

    for novel in reversed(novels):
        novel_id  = novel["novel_title"]
        last_chap = novel.get("last_chapter")
        if not last_chap:
            continue

        feed_type = args.feed              # "paid" or "free"
        feed_key  = f"{feed_type}_feed"    # "paid_feed" or "free_feed"
        url       = novel.get(feed_key)
        if not url:
            continue

        # map feed_type to the new state.json key
        # (this controls the generic skip check before parsing)
        if feed_type == "paid":
            completion_key = "paid_completion"
        else:
            completion_key = "free_completion"

        if state.get(novel_id, {}).get(completion_key):
            print(f"→ skipping {novel_id} ({completion_key}) — already notified")
            continue

        # parse RSS
        resp = requests.get(url)
        feed = feedparser.parse(resp.text)
        print(
            f"Parsing {feed_key} for {novel_id}: got {len(feed.entries)} entries "
            f"(Content-Type: {resp.headers.get('Content-Type')})"
        )

        # look for the last_chapter marker in feed entries
        for entry in feed.entries:
            # (optional) guard by novel title if using shared feed
            entry_title = (entry.get("title") or "").strip()
            if entry_title and entry_title != novel_id:
                continue
        
            base = entry.get("chapter") or entry.get("chapter", "") or ""
            ext  = entry.get("chaptername") or ""
        
            # 1) use combined string only for matching
            chap_match = f"{base} {ext}".strip()
        
            if last_chap not in chap_match:
                continue
        
            # 2) use a clean title for display (prefer base)
            chap_field = base.strip()

            # --- ONLY-FREE CASE (series with no paid feed at all) ---
            if feed_type == "free" and not novel.get("paid_feed"):
                # guard specifically for only_free_completion so we don't double announce
                if state.get(novel_id, {}).get("only_free_completion"):
                    print(f"→ skipping {novel_id} (only_free_completion) — already notified")
                    break

                # compute duration…
                if entry.get("published_parsed"):
                    chap_date = datetime(*entry.published_parsed[:6])
                elif entry.get("updated_parsed"):
                    chap_date = datetime(*entry.updated_parsed[:6])
                else:
                    chap_date = datetime.now()

                duration = get_duration(novel.get("start_date", ""), chap_date)

                msg = build_only_free_completion(novel, chap_field, entry.link, duration)
                print(f"→ Built message of {len(msg)} characters")

                success = safe_send_bot(bot_token, channel_id, msg)
                if success:
                    print(f"✔️ Sent only-free completion announcement for {novel_id}")
                    state.setdefault(novel_id, {})["only_free_completion"] = {
                        "chapter": chap_field,
                        "sent_at": datetime.now().isoformat()
                    }
                    save_state(state)
                else:
                    print(
                        f"→ Not marking {novel_id} as ‘only_free_completion’ "
                        f"because send failed"
                    )
                break

            # --- PAID COMPLETION CASE ---
            elif feed_type == "paid":
                # extra guard for paid_completion
                if state.get(novel_id, {}).get("paid_completion"):
                    print(f"→ skipping {novel_id} (paid_completion) — already notified")
                    break

                # compute duration…
                if entry.get("published_parsed"):
                    chap_date = datetime(*entry.published_parsed[:6])
                elif entry.get("updated_parsed"):
                    chap_date = datetime(*entry.updated_parsed[:6])
                else:
                    chap_date = datetime.now()

                duration = get_duration(novel.get("start_date", ""), chap_date)

                msg = build_paid_completion(novel, chap_field, entry.link, duration)
                print(f"→ Built message of {len(msg)} characters")

                success = safe_send_bot(bot_token, channel_id, msg)
                if success:
                    print(f"✔️ Sent paid-completion announcement for {novel_id}")
                    state.setdefault(novel_id, {})["paid_completion"] = {
                        "chapter": chap_field,
                        "sent_at": datetime.now().isoformat()
                    }
                    save_state(state)
                else:
                    print(
                        f"→ Not marking {novel_id} as ‘paid_completion’ "
                        f"because send failed"
                    )
                break

            # --- STANDARD FREE COMPLETION (series that also had a paid feed) ---
            elif feed_type == "free":
                # extra guard for free_completion
                if state.get(novel_id, {}).get("free_completion"):
                    print(f"→ skipping {novel_id} (free_completion) — already notified")
                    break

                msg = build_free_completion(novel, chap_field, entry.link)
                print(f"→ Built message of {len(msg)} characters")

                success = safe_send_bot(bot_token, channel_id, msg)
                if success:
                    print(f"✔️ Sent free-completion announcement for {novel_id}")
                    state.setdefault(novel_id, {})["free_completion"] = {
                        "chapter": chap_field,
                        "sent_at": datetime.now().isoformat()
                    }
                    save_state(state)
                else:
                    print(
                        f"→ Not marking {novel_id} as ‘free_completion’ "
                        f"because send failed"
                    )
                break


if __name__ == "__main__":
    main()
