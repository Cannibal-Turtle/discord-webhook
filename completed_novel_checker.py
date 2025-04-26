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
from novel_mappings import HOSTING_SITE_DATA

# ─── CONFIG ────────────────────────────────────────────────────────────────────
STATE_PATH  = "state.json"
BOT_TOKEN_ENV   = "DISCORD_BOT_TOKEN"
CHANNEL_ID_ENV  = "DISCORD_CHANNEL_ID"
COMPLETE_ROLE = "<@&1329391480435114005>"
# ────────────────────────────────────────────────────────────────────────────────

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
        "allowed_mentions": { "parse": ["roles"] },
        "flags": 4
    }
    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()

def safe_send_bot(bot_token: str, channel_id: str, content: str):
    """
    Try sending via bot, but catch HTTP errors so the rest of the script continues.
    """
    try:
        send_bot_message(bot_token, channel_id, content)
    except requests.HTTPError as e:
        status = e.response.status_code if (e.response and e.response.status_code) else "?"
        print(f"⚠️ Bot send failed with status {status}: {e}", file=sys.stderr)

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
    discord_url = novel.get("discord_role_url", "")
    count     = novel.get("chapter_count", "the entire series")
    comp_role = COMPLETE_ROLE
    DIV = "<a:purple_divider1:1365652778957144165>"
    divider_line = DIV * 12
  
    # normalize NBSP
    chap_text = chap_field.replace("\u00A0", " ")
    return (
        f"{role} | {comp_role} <a:HappyCloud:1365575487333859398>\n"
        "## ꧁ᐟᐟ ◌ೄ⟢  Completion Announcement  :blueberries: ˚. ᵎᵎ˖ˎˊ-\n"
        f"{divider_line}\n"
        f"***<a:kikilts_bracket:1365693072138174525>[{title}]({link})<a:lalalts_bracket:1365693058905014313>— officially completed!*** <a:Bow:1365575505171976246><a:whitesparklingstars2:1365569806966853664>\n\n"
        f"*The last chapter, [{chap_text}]({chap_link}), has now been released. <a:turtle_super_hyper:1365223449827737630>\n"
        f"After {duration} of updates, {title} is now fully translated with {count}! Thank you for coming on this journey and for your continued support <:turtle_plead:1365223487274352670> You can now visit {host} to binge all advance releases~*<a:Heart:1365575427724283944>"
        f"<a:Paws:1365676154865979453>{'<:FF_Divider_Pink:1365575626194681936>' * 6}\n"
        f"-# Check out other translated projects at {discord_url} and react to get the latest updates <a:LoveLetter:1365575475841339435>"
    )
  
def build_free_completion(novel, chap_field, chap_link):
    role      = novel.get("role_mention", "").strip()
    title     = novel.get("novel_title", "")
    link      = novel.get("novel_link", "")
    host      = novel.get("host", "")
    discord_url = novel.get("discord_role_url", "")
    count     = novel.get("chapter_count", "the entire series")
    comp_role = COMPLETE_ROLE
    DIV = "<a:purple_divider1:1365652778957144165>"
    divider_line = DIV * 12

    # normalize NBSP
    chap_text = chap_field.replace("\u00A0", " ")
    return (
        f"{role} | {comp_role} <a:HappyCloud:1365575487333859398>\n"
        "## 𐔌  Announcing: Complete Series Unlocked ,, :cherries: — 𝝑𝝔  ꒱\n"
        f"{divider_line}\n"
        f"***<a:kikilts_bracket:1365693072138174525>[{title}]({link})<a:lalalts_bracket:1365693058905014313>— complete access granted!*** <a:Bow:1365575505171976246><a:whitesparklingstars2:1365569806966853664>\n\n"
        f"*All {count} has been unlocked and ready for you to binge—completely free!\n"
        f"Thank you all for your amazing support   <:green_turtle_heart:1365264636064305203>\n"
        f"Head over to {host} to dive straight in~*<a:Heart:1365575427724283944>"
        f"<a:Paws:1365676154865979453>{'<:FF_Divider_Pink:1365575626194681936>' * 6}\n"
        f"-# Check out other translated projects at {discord_url} and react to get the latest updates <a:LoveLetter:1365575475841339435>"
    )

def build_only_free_completion(novel, chap_field, chap_link, duration):
    role        = novel.get("role_mention", "").strip()
    comp_role   = COMPLETE_ROLE
    title       = novel.get("novel_title", "")
    link        = novel.get("novel_link", "")
    host        = novel.get("host", "")
    discord_url = novel.get("discord_role_url", "")
    count       = novel.get("chapter_count", "the entire series")
    DIV = "<a:purple_divider1:1365652778957144165>"
    divider_line = DIV * 12

    # normalize NBSP
    chap_text = chap_field.replace("\u00A0", " ")

    return (
        f"{role} | {comp_role} <a:HappyCloud:1365575487333859398>\n"
        "## ⁺‧ ༻•┈๑☽₊˚ ⌞Completion Announcement⋆ཋྀ ˚₊‧⁺ :kiwi: ∗༉‧₊˚\n"
        f"{divider_line}\n"
        f"***<a:kikilts_bracket:1365693072138174525>[{title}]({link})<a:lalalts_bracket:1365693058905014313>— officially completed!*** <a:Bow:1365575505171976246><a:whitesparklingstars2:1365569806966853664>\n\n"
        f"*The last chapter, [{chap_text}]({chap_link}), has now been released. <a:turtle_super_hyper:1365223449827737630>\n"
        f"After {duration} of updates, {title} is now fully translated with {count}! Thank you for coming on this journey and for your continued support <:d_greena_luv_turtle:365263712549736448> You can now visit {host} to binge on all the releases~*<a:Heart:1365575427724283944>"
        f"<a:Paws:1365676154865979453>{'<:FF_Divider_Pink:1365575626194681936>' * 6}\n"
        f"-# Check out other translated projects at {discord_url} and react to get the latest updates <a:LoveLetter:1365575475841339435>"
    )

def load_novels():
    """Pull novels directly from HOSTING_SITE_DATA."""
    novels = []
    for host, host_data in HOSTING_SITE_DATA.items():
        for title, details in host_data.get("novels", {}).items():
            last = details.get("last_chapter")
            # skip if no completion marker
            if not last:
                continue
            free = details.get("free_feed")
            paid = details.get("paid_feed")
            if not (free or paid):
                continue
            novels.append({
                "novel_title":   title,
                "role_mention":  details.get("discord_role_id", ""),
                "host":          host,
                "novel_link":    details.get("novel_url", ""),
                "chapter_count": details.get("chapter_count", ""),
                "last_chapter":  last,
                "start_date":    details.get("start_date", ""),
                "free_feed":     free,
                "paid_feed":     paid,
                "discord_role_url": details.get("discord_role_url", ""),
            })
    return novels

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", choices=["paid","free"], required=True)
    args = parser.parse_args()

    bot_token  = os.getenv(BOT_TOKEN_ENV)
    channel_id = os.getenv(CHANNEL_ID_ENV)
    if not (bot_token and channel_id):
        sys.exit("❌ Missing DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID")

    state  = load_state()
    novels = load_novels()

    for novel in novels:
        novel_id = novel["novel_title"]
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
            if last_chap not in chap_field:
                continue

            # --- ONLY-FREE (no paid_feed) ---
            if feed_type == "free" and not novel.get("paid_feed"):
                if state.get(novel_id, {}).get("only_free"):
                    print(f"→ skipping {novel_id} (only_free) — already notified")
                    break

                # compute duration…
                if entry.get("published_parsed"):
                    chap_date = datetime(*entry.published_parsed[:6])
                elif entry.get("updated_parsed"):
                    chap_date = datetime(*entry.updated_parsed[:6])
                else:
                    chap_date = datetime.now()
                duration = get_duration(novel.get("start_date",""), chap_date)

                msg = build_only_free_completion(novel, chap_field, entry.link, duration)
                if bot_token and channel_id:
                    safe_send_bot(bot_token, channel_id, msg)
                    print(f"✔️ Sent only-free completion announcement for {novel_id}")
                else:
                    print("⚠️ Bot token or channel ID missing; skipped bot post", file=sys.stderr)
                state.setdefault(novel_id, {})["only_free"] = {
                    "chapter": chap_field,
                    "sent_at": datetime.now().isoformat()
                }
                save_state(state)
                break

            # --- PAID COMPLETE ---
            elif feed_type == "paid":
                if state.get(novel_id, {}).get("paid"):
                    print(f"→ skipping {novel_id} (paid) — already notified")
                    break

                # compute duration…
                if entry.get("published_parsed"):
                    chap_date = datetime(*entry.published_parsed[:6])
                elif entry.get("updated_parsed"):
                    chap_date = datetime(*entry.updated_parsed[:6])
                else:
                    chap_date = datetime.now()
                duration = get_duration(novel.get("start_date",""), chap_date)

                msg = build_paid_completion(novel, chap_field, entry.link, duration)
                if bot_token and channel_id:
                    safe_send_bot(bot_token, channel_id, msg)
                    print(f"✔️ Sent paid-completion announcement for {novel_id}")
                else:
                    print("⚠️ Bot token or channel ID missing; skipped bot post", file=sys.stderr)
                state.setdefault(novel_id, {})["paid"] = {
                    "chapter": chap_field,
                    "sent_at": datetime.now().isoformat()
                }
                save_state(state)
                break

            # --- STANDARD FREE (has paid_feed) ---
            elif feed_type == "free":
                if state.get(novel_id, {}).get("free"):
                    print(f"→ skipping {novel_id} (free) — already notified")
                    break

                msg = build_free_completion(novel, chap_field, entry.link)
                if bot_token and channel_id:
                    safe_send_bot(bot_token, channel_id, msg)
                    print(f"✔️ Sent free-completion announcement for {novel_id}")
                else:
                    print("⚠️ Bot token or channel ID missing; skipped bot post", file=sys.stderr)
                state.setdefault(novel_id, {})["free"] = {
                    "chapter": chap_field,
                    "sent_at": datetime.now().isoformat()
                }
                save_state(state)
                break

if __name__ == "__main__":
    main()
