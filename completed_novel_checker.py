#!/usr/bin/env python3
"""
completed_novel_checker.py

Run this via an external repository_dispatch (or git hook) whenever your feeds are regenerated.
It will fire exactly one “completion” message per novel as soon as the configured last_chapter
appears in either the paid or free feed.
"""
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

def build_completion_message(novel, chap_field, chap_link):
    role       = novel.get("role_mention", "").strip()
    comp_role  = novel.get("complete_role_mention", "").strip()
    title      = novel["novel_title"]
    novel_link = novel.get("novel_link", "")
    host       = novel.get("host", "")
    return (
        f"{role} | {comp_role}\n\n"
        "## ꧁ᐟᐟ ⟢  Completion Announcement  :blueberries: ˚. ᵎᵎ˖ˎˊ-\n"
        "◈· ─ · ─ · ─ · ❁ · ─ ·𖥸· ─ · ❁ · ─ · ─ · ─ ·◈\n"
        f"***『[{title}]({novel_link})』officially completed***\n\n"
        f"*The last chapter, [{chap_field}](<{chap_link}>), has now been released. "
        f"After months of updates, {title} is now fully translated! Thank you for coming on this journey "
        "and for your continued support :pandalove: You can now visit "
        f"{host} to binge all advance releases~♡*"
    )

def main():
    webhook_url = os.getenv(WEBHOOK_ENV)
    if not webhook_url:
        print(f"ERROR: environment variable {WEBHOOK_ENV} is not set", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    novels = config.get("novels", [])
    if not novels:
        print("No novels defined in config.json. Exiting.")
        return

    for novel in novels:
        last_chap = novel.get("last_chapter")
        if not last_chap:
            # skip entries without a last_chapter
            continue

        for feed_key in ("paid_feed", "free_feed"):
            feed_url = novel.get(feed_key)
            if not feed_url:
                continue

            feed = feedparser.parse(feed_url)
            if feed.bozo:
                print(f"WARNING: could not parse {feed_key} ({feed_url}): {feed.bozo_exception}", file=sys.stderr)
                continue

            for entry in feed.entries:
                # grab chaptername or fall back to chapter
                chap_field = entry.get("chaptername") or entry.get("chapter", "")
                if last_chap in chap_field:
                    chap_link = entry.get("link", "")
                    msg = build_completion_message(novel, chap_field, chap_link)

                    print(f"→ MATCH for “{novel['novel_title']}” in {feed_key}: {chap_field}")
                    try:
                        send_discord_message(webhook_url, msg)
                        print("✔️ Sent completion announcement.")
                    except Exception as e:
                        print(f"ERROR sending Discord message: {e}", file=sys.stderr)
                        sys.exit(1)
                    # stop checking other feeds for this novel
                    break
            else:
                # no break: continue to next feed
                continue
            # we found and sent for this novel → move to next novel
            break

if __name__ == "__main__":
    main()
