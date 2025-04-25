#!/usr/bin/env python3
import os
import sys
from completed_novel_checker import build_paid_completion, safe_send_bot


def main():
    # 1) retrieve your Bot credentials from env
    bot_token  = os.getenv("BOT_TOKEN")
    channel_id = os.getenv("CHANNEL_ID")
    if not bot_token or not channel_id:
        print("⚠️ BOT_TOKEN and CHANNEL_ID must be set", file=sys.stderr)
        sys.exit(1)

    # 2) construct a fake novel payload for testing
    novel = {
        "role_mention":    "<@&1329391480435114005>",
        "novel_title":     "Test Novel",
        "novel_link":      "https://example.com/novel",
        "host":            "ExampleHost",
        "discord_role_url":"https://discord.com/channels/...",
        "chapter_count":   "42 chapters",
    }

    # 3) build & send the paid-completion message
    msg = build_paid_completion(
        novel,
        chap_field="Chapter 42",
        chap_link="https://example.com/novel/chapter-42",
        duration="a fortnight"
    )

    safe_send_bot(bot_token, channel_id, msg)


if __name__ == "__main__":
    main()
