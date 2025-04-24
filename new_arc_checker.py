import requests
import feedparser
import os
import json
import re
import sys
from novel_mappings import HOSTING_SITE_DATA, get_nsfw_novels

ONGOING_ROLE = "<@&1329502951764525187>"
NSFW_ROLE_ID = "<@&1343352825811439616>"
WEBHOOK_ENV     = "DISCORD_WEBHOOK"
BOT_TOKEN_ENV   = "DISCORD_BOT_TOKEN"
CHANNEL_ID_ENV  = "DISCORD_CHANNEL_ID"

# === HELPER FUNCTIONS ===

def send_bot_message(bot_token: str, channel_id: str, content: str):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type":  "application/json"
    }
    payload = {
        "content": content,
        "allowed_mentions": {"parse": ["roles"]},
        "flags": 4
    }
    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()

def safe_send_webhook(webhook_url: str, content: str):
    try:
        requests.post(webhook_url, json={
            "content": content,
            "flags": 4,
            "allowed_mentions": {"parse": ["roles"]}
        }).raise_for_status()
    except requests.RequestException as e:
        print(f"⚠️ Webhook send failed: {e}", file=sys.stderr)

def safe_send_bot(bot_token: str, channel_id: str, content: str):
    try:
        send_bot_message(bot_token, channel_id, content)
    except requests.RequestException as e:
        print(f"⚠️ Bot send failed: {e}", file=sys.stderr)

def load_history(history_file):
    """Loads the novel's arc history from JSON file."""
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
            history.setdefault("last_announced", "")
        print(f"📂 Loaded history from {history_file}: {len(history['unlocked'])} unlocked, {len(history['locked'])} locked, last_announced={history['last_announced']}")
        return history
    else:
        print(f"📂 No history file found at {history_file}, starting fresh")
        return {"unlocked": [], "locked": [], "last_announced": ""}

def save_history(history, history_file):
    """Saves the novel's arc history to JSON file with proper encoding."""
    print(f"📂 Saving history to {history_file} (unlocked={len(history['unlocked'])}, locked={len(history['locked'])}, last_announced={history['last_announced']})")
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)
    print(f"✅ Successfully updated history file: {history_file}")

def commit_history_update(history_file):
    """Commits and pushes the updated history file to GitHub."""
    print(f"📌 Committing changes for {history_file}...")
    os.system("git config --global user.name 'GitHub Actions'")
    os.system("git config --global user.email 'actions@github.com'")
    os.system("git status")
    os.system(f"git add {history_file}")
    changes_detected = os.system("git diff --staged --quiet")
    if changes_detected != 0:
        os.system(f"git commit -m 'Auto-update: {history_file}'")
        print(f"✅ Committed changes for {history_file}")
    else:
        print(f"⚠️ No changes detected in {history_file}, skipping commit.")
    push_status = os.system("git push origin main")
    if push_status != 0:
        print("❌ Git push failed. Trying again with force...")
        os.system("git push origin main --force")

def clean_feed_title(raw_title):
    """Removes extra characters from feed titles."""
    return raw_title.replace("*", "").strip()

def format_stored_title(title):
    """Formats arc titles for Discord messages."""
    match = re.match(r"(【Arc\s+\d+】)\s*(.*)", title)
    return f"**{match.group(1)}**{match.group(2)}" if match else f"**{title}**"

def extract_arc_number(title):
    """Extracts arc number from a title that begins with 【Arc N】."""
    match = re.search(r"【Arc\s*(\d+)】", title)
    return int(match.group(1)) if match else None

def deduplicate(lst):
    """Removes duplicates while preserving order."""
    seen = set()
    result = []
    for x in lst:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result

def nsfw_detected(feed_entries, novel_title):
    """Checks if NSFW category exists for this novel."""
    for entry in feed_entries:
        if novel_title.lower() in entry.get("title", "").lower() and "nsfw" in entry.get("category","").lower():
            print(f"⚠️ NSFW detected in entry: {entry.get('title')}")
            return True
    return False

def extract_arc_title(nameextend):
    """Strips trailing ' 001', '(1)', or '.1' from the raw nameextend."""
    # Remove leading/trailing stars
    clean = nameextend.strip("* ").strip()
    # Remove suffix markers
    clean = re.sub(r"(?:\s+001|\(1\)|\.\s*1)$", "", clean).strip()
    return clean

def strip_any_number_prefix(s: str) -> str:
    """
    Remove any leading text up through the first run of digits (plus
    any immediately following punctuation and spaces).
    E.g.  
      "【Arc 22】Foo"    → "Foo"  
      "Arc 22: Foo"     → "Foo"  
      "World10 - Bar"   → "Bar"  
      "Prefix 3) Baz"   → "Baz"
    """
    return re.sub(r"^.*?\d+[^\w\s]*\s*", "", s)

def next_arc_number(history):
    """Returns last announced arc number + 1, or 1 if none."""
    last = history.get("last_announced", "")
    n = extract_arc_number(last)
    if n:
        print(f"🔢 Last announced arc is {n}, so next will be {n+1}")
        return n + 1
    # fallback: scan unlocked+locked
    nums = []
    for section in ("unlocked","locked"):
        for title in history[section]:
            m = extract_arc_number(title)
            if m:
                nums.append(m)
    m = max(nums) if nums else 0
    print(f"🔢 No valid last_announced; max seen in history is {m}, so next will be {m+1}")
    return m + 1

# === PROCESS NOVEL FUNCTION ===

def process_arc(novel):
    print(f"\n=== Processing novel: {novel['novel_title']} ===")
    # 0. parse feeds
    free_feed = feedparser.parse(novel["free_feed"])
    paid_feed = feedparser.parse(novel["paid_feed"])
    print(f"🌐 Fetched feeds: {len(free_feed.entries)} free entries, {len(paid_feed.entries)} paid entries")

    # 1) NSFW check
    is_nsfw = (
        novel["novel_title"] in get_nsfw_novels()
        or nsfw_detected(free_feed.entries + paid_feed.entries, novel["novel_title"])
    )
    print(f"🕵️ is_nsfw={is_nsfw} for {novel['novel_title']}")
    base_mention = novel["role_mention"] + (f" | {NSFW_ROLE_ID}" if is_nsfw else "")

    history_file = novel.get("history_file")
    if not history_file:
        print(f"No history_file configured for '{novel['novel_title']}', skipping arcs.")
        return

    # 2. load history immediately after fetching feeds
    history = load_history(history_file)

    # helper to detect new‐arc markers
    def is_new_marker(raw):
        # word-boundary 001, (1), or trailing .1
        return bool(re.search(r"\b001\b|\(1\)|\.\s*1$", raw))

    # 1. extract new‐arc bases
    def extract_new_bases(feed):
        bases = []
        for e in feed.entries:
            # 1) normalize any NBSPs and strip
            raw_vol    = e.get("volume", "").replace("\u00A0", " ").strip()
            raw_extend = e.get("nameextend", "").replace("\u00A0", " ").strip()
            raw_chap   = e.get("chaptername", "").replace("\u00A0", " ").strip()
    
            # 2) skip anything that doesn’t look like “001” / “(1)” / “.1”
            if not (is_new_marker(raw_extend) or is_new_marker(raw_chap)):
                continue
    
            # 3) pick your base name in priority order
            if raw_vol:
                base = clean_feed_title(raw_vol)
            elif raw_extend:
                base = extract_arc_title(raw_extend)
            else:
                base = raw_chap
    
            # 4) finally strip off any leading “Arc N” prefix, etc.
            base = strip_any_number_prefix(base)
            bases.append(base)
    
        return bases

    free_new = extract_new_bases(free_feed)
    paid_new = extract_new_bases(paid_feed)
    print(f"🔍 Detected {len(free_new)} new free arcs, {len(paid_new)} new paid arcs")

    # 3. unlock free arcs
    for base in free_new:
        for full in history["locked"][:]:
            if full.endswith(base):
                history["locked"].remove(full)
                if full not in history["unlocked"]:
                    history["unlocked"].append(full)
                    print(f"🔓 Unlocked arc: {full}")
                break

    # 4. lock paid arcs (new ones)
    seen_bases = [re.sub(r"^【Arc\s*\d+】", "", f) for f in history["unlocked"] + history["locked"]]
    for base in paid_new:
        if base not in seen_bases:
            n = next_arc_number(history)
            full = f"【Arc {n}】{base}"
            history["locked"].append(full)
            print(f"🔐 New locked arc: {full}")

    # dedupe & save
    history["unlocked"] = deduplicate(history["unlocked"])
    history["locked"]   = deduplicate(history["locked"])
    save_history(history, novel["history_file"])

    # 5. announce the newest locked arc
    new_full = history["locked"][-1] if history["locked"] else None
    if not new_full:
        print("ℹ️ No locked arcs to announce.")
        return
    if new_full == history.get("last_announced"):
        print(f"✅ Already announced: {new_full}")
        return

    # update last_announced & commit
    history["last_announced"] = new_full
    save_history(history, novel["history_file"])
    commit_history_update(novel["history_file"])
    print(f"📌 Announcing new locked arc: {new_full}")

    # number for header
    world_number = extract_arc_number(new_full)

    # build message
    unlocked_md = "\n".join(format_stored_title(t) for t in history["unlocked"])
    locked_lines = [format_stored_title(t) for t in history["locked"]]
    locked_lines = deduplicate(locked_lines)
    if locked_lines:
        locked_lines[-1] = f"☛{locked_lines[-1]}"
    locked_md = "\n".join(locked_lines)

    message = (
        f"{base_mention} | {ONGOING_ROLE}\n"
        "## :loudspeaker: NEW ARC ALERT˚ · .˚ ༘:butterfly:⋆｡˚\n"
        f"***《World {world_number}》is Live for***\n"
        f"### [{novel['novel_title']}]({novel['novel_link']}) <:Hehe:1329429547229122580>\n"
        "❀° ┄───────────────────────╮\n"
        "**`Unlocked 🔓`**\n"
        f"||{unlocked_md}||\n\n"
        "**`Locked 🔐`**\n"
        f"||{locked_md}||\n"
        "╰───────────────────────┄ °❀\n"
        f"> *Advance access is ready for you on {novel['host']}! :rose:*\n"
        "✎﹏﹏﹏﹏﹏﹏﹏﹏\n"
        f"-# React to the {novel['custom_emoji']} @ {novel['discord_role_url']} to get notified on updates and announcements~"
    )

    # === SEND DISCORD NOTIFICATION ===
    payload = {
        "content": message,
        "allowed_mentions": {"parse": ["roles"]},
        "flags": 4
    }
    webhook_url = os.getenv(WEBHOOK_ENV)
    bot_token   = os.getenv(BOT_TOKEN_ENV)
    channel_id  = os.getenv(CHANNEL_ID_ENV)

    # send via webhook (if configured)
    if webhook_url:
        safe_send_webhook(webhook_url, message)
        print(f"✅ Webhook notification sent for: {new_full}")
    else:
        print("⚠️ DISCORD_WEBHOOK not set, skipped webhook post")

    # send via bot (if configured)
    if bot_token and channel_id:
        safe_send_bot(bot_token, channel_id, message)
        print(f"✅ Bot notification sent for: {new_full}")
    else:
        print("⚠️ Bot token or channel ID missing, skipped bot post")
        
# === LOAD & RUN ===
if __name__ == "__main__":
    for host, host_data in HOSTING_SITE_DATA.items():
        for title, d in host_data.get("novels", {}).items():
            if not d.get("free_feed") or not d.get("paid_feed"):
                continue
            novel = {
                "novel_title":     title,
                "role_mention":    d.get("discord_role_id", ""),
                "host":            host,
                "free_feed":       d["free_feed"],
                "paid_feed":       d["paid_feed"],
                "novel_link":      d.get("novel_url", ""),
                "custom_emoji":    d.get("custom_emoji", ""),
                "discord_role_url":d.get("discord_role_url", ""),
                "history_file":    d.get("history_file", "")
            }
            process_arc(novel)
