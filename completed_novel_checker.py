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
    resp = requests.post(webhook_url, json={"content": content})
    resp.raise_for_status()


def build_paid_completion(novel, chap_field, chap_link):
    role       = novel.get("role_mention", "").strip()
    comp_role  = novel.get("complete_role_mention", "").strip()
    title      = novel.get("novel_title", "")
    link       = novel.get("novel_link", "")
    host       = novel.get("host", "")

    return (
        f"{role} | {comp_role}\n"
        "## ꧁ᐟᐟ ⟢  Completion Announcement  :blueberries: ˚. ᵎᵎ˖ˎˊ-\n"
        "◈· ─ · ─ · ─ · ❁ · ─ ·𖥸· ─ · ❁ · ─ · ─ · ─ ·◈\n"
        f"***『[{title}]({link})』officially completed***\n\n"
        f"*The last chapter, [{chap_field}](<{chap_link}>), has now been released.\n"
        f"After months of updates, {title} is now fully translated! Thank you for coming on this journey and for your continued support :pandalove: You can now visit {host} to binge all advance releases~♡*"
    )


def build_free_completion(novel, chap_field, chap_link):
    role       = novel.get("role_mention", "").strip()
    comp_role  = novel.get("complete_role_mention", "").strip()
    title      = novel.get("novel_title", "")
    link       = novel.get("novel_link", "")
    host       = novel.get("host", "")
    count      = novel.get("chapter_count", "the entire series")

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
        print(f"ERROR: {WEBHOOK_ENV} not set", file=sys.stderr)
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
                chap_link = entry.get("link", "")
                if args.feed == "paid":
                    msg = build_paid_completion(novel, chap_field, chap_link)
                else:
                    msg = build_free_completion(novel, chap_field, chap_link)

                print(f"→ [{key}] MATCH for “{novel.get('novel_title')}”: {chap_field}")
                try:
                    send_discord_message(webhook_url, msg)
                    print(f"✔️ Sent {args.feed}-completion announcement.")
                except Exception as e:
                    print(f"ERROR sending {args.feed}-completion message: {e}", file=sys.stderr)
                    sys.exit(1)
                return


if __name__ == "__main__":
    main()
