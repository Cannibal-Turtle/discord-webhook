#!/usr/bin/env python3
"""
completed_novel_checker.py

Run this via your repository_dispatch (or on-demand) whenever your feeds are regenerated.
It will fire a “paid complete” announcement when the paid_feed hits last_chapter,
and a separate “free complete” announcement when the free_feed hits last_chapter.
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
from datetime import datetime
from dateutil.relativedelta import relativedelta

CONFIG_PATH = "config.json"
STATE_PATH  = "state.json"
WEBHOOK_ENV = "DISCORD_WEBHOOK"
COMPLETE_ROLE = "<@&1329391480435114005>"

def load_state(path=STATE_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_state(state, path=STATE_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
      
def load_config(path=CONFIG_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: cannot open {path}", file=sys.stderr)
        sys.exit(1)

def send_discord_message(webhook_url: str, content: str):
    # Include allowed_mentions so webhooks color role pings correctly
    payload = {
        "content": content,
        "allowed_mentions": { "parse": ["roles"] },
        "flags": 4
    }
    resp = requests.post(webhook_url, json=payload)
    resp.raise_for_status()

def get_duration(start_date_str: str, end_date: datetime) -> str:
    """
    Converts a start date to a human-readable duration compared to end date.
    Uses 'more than' if days exceed clean year/month/week thresholds.
    """
    day, month, year = map(int, start_date_str.split("/"))
    start = datetime(year, month, day)
    delta = relativedelta(end_date, start)

    years = delta.years
    months = delta.months
    days = delta.days

    # Handle year and month logic
    if years > 0:
        if months > 0:
            if days > 0:
                return f"more than {'a' if years == 1 else years} year{'s' if years > 1 else ''} and {'a' if months == 1 else months} month{'s' if months > 1 else ''}"
            return f"{'a' if years == 1 else years} year{'s' if years > 1 else ''} and {'a' if months == 1 else months} month{'s' if months > 1 else ''}"
        else:
            if days > 0:
                return f"more than {'a' if years == 1 else years} year{'s' if years > 1 else ''}"
            return f"{'a' if years == 1 else years} year{'s' if years > 1 else ''}"
    elif months > 0:
        if days > 0:
            return f"more than {'a' if months == 1 else months} month{'s' if months > 1 else ''}"
        return f"{'a' if months == 1 else months} month{'s' if months > 1 else ''}"

    # Handle week and day logic for durations less than a month
    weeks = days // 7
    remaining_days = days % 7

    if weeks > 0:
        if remaining_days > 0:
            return f"more than {weeks} week{'s' if weeks != 1 else ''}"
        return f"{weeks} week{'s' if weeks != 1 else ''}"
    elif remaining_days > 0:
        return f"more than a week"
    else:
        return "less than a week"

def build_paid_completion(novel, chap_field, chap_link, duration: str):
    role      = novel.get("role_mention", "").strip()
    title     = novel.get("novel_title", "")
    link      = novel.get("novel_link", "")
    host      = novel.get("host", "")
    count     = novel.get("chapter_count", "the entire series")
    comp_role = COMPLETE_ROLE

    # normalize NBSP
    chap_text = chap_field.replace("\u00A0", " ")
    return (
        f"{role} | {comp_role}\n"
        "## ꧁ᐟᐟ ⟢  Completion Announcement  :blueberries: ˚. ᵎᵎ˖ˎˊ-\n"
        "◈· ─ · ─ · ─ · ❁ · ─ ·𖥸· ─ · ❁ · ─ · ─ · ─ ·◈\n"
        f"***『[{title}]({link})』— officially completed!***\n\n"
        f"*The last chapter, [{chap_text}]({chap_link}), has now been released.\n"
        f"After {duration} of updates, {title} is now fully translated with {count}! Thank you for coming on this journey and for your continued support :pandalove: You can now visit {host} to binge all advance releases~♡*"
    )

def build_free_completion(novel, chap_field, chap_link):
    role      = novel.get("role_mention", "").strip()
    title     = novel.get("novel_title", "")
    link      = novel.get("novel_link", "")
    host      = novel.get("host", "")
    count     = novel.get("chapter_count", "the entire series")
    comp_role = COMPLETE_ROLE

    # normalize NBSP
    chap_text = chap_field.replace("\u00A0", " ")
    return (
        f"{role} | {comp_role}\n"
        "## 𐔌  Announcing: Complete Series Unlocked ,, :cherries: — 𝝑𝝔  ꒱\n"
        "◈· ─ · ─ · ─ · ❁ · ─ ·𖥸· ─ · ❁ · ─ · ─ · ─ ·◈\n"
        f"***『[{title}]({link})』— complete access granted!***\n\n"
        f"*All {count} has been unlocked and ready for you to binge—completely free!  \n"
        f"Thank you all for your amazing support   :green_turtle_heart:  \n"
        f"Head over to {host} to dive straight in~♡*"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", choices=["paid","free"], required=True)
    args = parser.parse_args()

    webhook_url = os.getenv(WEBHOOK_ENV)
    if not webhook_url:
        print(f"ERROR: environment variable {WEBHOOK_ENV} is not set", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    state  = load_state()

    for novel in config.get("novels", []):
        novel_id  = novel.get("novel_id", novel.get("novel_title"))
        last_chap = novel.get("last_chapter")
        if not last_chap:
            continue

        feed_type = args.feed
        feed_key  = f"{feed_type}_feed"
        url       = novel.get(feed_key)
        if not url:
            continue

        # skip if already sent
        if state.get(novel_id, {}).get(feed_type):
            print(f"→ skipping {novel_id} ({feed_type}) — already notified")
            continue

        # parse RSS
        feed = feedparser.parse(url)
        if feed.bozo:
            print(f"WARNING: could not parse {feed_key}: {feed.bozo_exception}", file=sys.stderr)
            continue

        # look for last_chapter
        for entry in feed.entries:
            chap_field = entry.get("chaptername") or entry.get("chapter", "")
            if last_chap in chap_field:
                # build message
                if feed_type == "paid":
                    if entry.get("published_parsed"):
                        chap_date = datetime(*entry.published_parsed[:6])
                    elif entry.get("updated_parsed"):
                        chap_date = datetime(*entry.updated_parsed[:6])
                    else:
                        chap_date = datetime.now()
                    duration = get_duration(novel.get("start_date",""), chap_date)
                    msg = build_paid_completion(novel, chap_field, entry.link, duration)
                else:
                    msg = build_free_completion(novel, chap_field, entry.link)

                # send and record
                send_discord_message(webhook_url, msg)
                print(f"✔️ Sent {feed_type}-completion announcement for {novel_id}")

                state.setdefault(novel_id, {})[feed_type] = {
                    "chapter": chap_field,
                    "sent_at":  datetime.now().isoformat()
                }
                save_state(state)
                break

if __name__ == "__main__":
    main()
