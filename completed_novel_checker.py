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
WEBHOOK_ENV = "DISCORD_WEBHOOK"

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
    comp_role = novel.get("complete_role_mention", "").strip()
    title     = novel.get("novel_title", "")
    link      = novel.get("novel_link", "")
    host      = novel.get("host", "")
    count     = novel.get("chapter_count", "the entire series")

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
    comp_role = novel.get("complete_role_mention", "").strip()
    title     = novel.get("novel_title", "")
    link      = novel.get("novel_link", "")
    host      = novel.get("host", "")
    count     = novel.get("chapter_count", "the entire series")

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
    parser.add_argument(
        "--feed",
        choices=["paid", "free"],
        required=True,
        help="Which feed to check: 'paid' or 'free'"
    )
    args = parser.parse_args()

    webhook_url = os.getenv(WEBHOOK_ENV)
    if not webhook_url:
        print(f"ERROR: environment variable {WEBHOOK_ENV} is not set", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    for novel in config.get("novels", []):
        last_chap = novel.get("last_chapter")
        if not last_chap:
            continue

        key = f"{args.feed}_feed"
        url = novel.get(key)
        if not url:
            continue

        feed = feedparser.parse(url)
        if feed.bozo:
            print(f"WARNING: could not parse {key}: {feed.bozo_exception}", file=sys.stderr)
            continue

        for entry in feed.entries:
            chap_field = entry.get("chaptername") or entry.get("chapter", "")
            if last_chap in chap_field:
                # normalize NBSP
                chap_text = chap_field.replace("\u00A0", " ")
                chap_link = entry.get("link", "")

                print(f"→ [{key}] MATCH for “{novel.get('novel_title')}”: {chap_text}")

                # determine chapter date
                if entry.get("published_parsed"):
                    chap_date = datetime(*entry.published_parsed[:6])
                elif entry.get("updated_parsed"):
                    chap_date = datetime(*entry.updated_parsed[:6])
                else:
                    chap_date = datetime.now()
    
                # compute duration
                start_date = novel.get("start_date", "")
                duration_str = get_duration(start_date, chap_date)
    
                # build message
                if args.feed == "paid":
                    msg = build_paid_completion(novel, chap_field, entry.get("link", ""), duration_str)
                else:
                    msg = build_free_completion(novel, chap_field, entry.get("link", ""))
    
                # send  log
                try:
                    send_discord_message(webhook_url, msg)
                    print(f"✔️ Sent {args.feed}-completion announcement.")
                except Exception as e:
                    print(f"ERROR sending {args.feed}-completion message: {e}", file=sys.stderr)
                    sys.exit(1)
    
                return


if __name__ == "__main__":
    main()
