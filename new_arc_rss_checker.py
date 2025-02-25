import requests
import feedparser
import os
import json
import re

# === HELPER FUNCTIONS ===
def load_history(history_file):
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            return json.load(f)
    else:
        return {"unlocked": [], "locked": [], "last_announced": ""}

def save_history(history, history_file):
    with open(history_file, "w") as f:
        json.dump(history, f, indent=4)

def clean_feed_title(raw_title):
    return raw_title.replace("*", "").strip()

def format_stored_title(title):
    """
    Expected stored title: "【Arc 16】 The Abandoned Supporting Female Role"
    Returns: "**【Arc 16】** The Abandoned Supporting Female Role"
    """
    match = re.match(r"(【Arc\s+\d+】)\s*(.*)", title)
    return f"**{match.group(1)}**{match.group(2)}" if match else f"**{title}**"

def extract_arc_number(title):
    match = re.search(r"【Arc\s*(\d+)】", title)
    return int(match.group(1)) if match else None

def deduplicate(lst):
    seen = set()
    return [x for x in lst if not (x in seen or seen.add(x))]

def nsfw_detected(feed_entries, novel_title):
    """
    Check if any entry that matches the given novel_title has a category containing "nsfw".
    Returns True if found, otherwise False.
    """
    for entry in feed_entries:
        if novel_title.lower() in entry.get("title", "").lower():
            if "nsfw" in entry.get("category", "").lower():
                return True
    return False

def extract_arc_title(nameextend):
    """
    Extracts the arc title by removing " 001" or "(1)" if present.
    """
    for suffix in [" 001", "(1)"]:
        if suffix in nameextend:
            return clean_feed_title(nameextend.split(suffix)[0])
    return clean_feed_title(nameextend)

# === PROCESS NOVEL FUNCTION ===
def process_novel(novel):
    # Unpack novel configuration.
    free_feed_url = novel["free_feed"]
    paid_feed_url = novel["paid_feed"]
    discord_webhook = os.getenv("DISCORD_WEBHOOK")
    role_mention = novel["role_mention"]
    novel_title = novel["novel_title"]
    novel_link = novel["novel_link"]
    host = novel["host"]
    custom_emoji = novel["custom_emoji"]
    discord_role_url = novel["discord_role_url"]
    history_file = novel["history_file"]

    # Fetch feeds.
    free_feed = feedparser.parse(free_feed_url)
    paid_feed = feedparser.parse(paid_feed_url)

    # Detect NSFW flag
    if nsfw_detected(free_feed.entries, novel_title):
        role_mention = f"{role_mention} <@&1329502951764525187> <@&1343352825811439616>"

    # Extract arcs
    free_arcs_feed = [extract_arc_title(entry.get("nameextend", ""))
                      for entry in free_feed.entries if " 001" in entry.get("nameextend", "") or "(1)" in entry.get("nameextend", "")]

    paid_arcs_feed = [extract_arc_title(entry.get("nameextend", ""))
                      for entry in paid_feed.entries if " 001" in entry.get("nameextend", "") or "(1)" in entry.get("nameextend", "")]

    # Load persistent history.
    history = load_history(history_file)

    # Update history:
    # - Arcs from free feed go to "unlocked" (and are removed from "locked" if present).
    for arc in free_arcs_feed:
        if arc not in history["unlocked"]:
            history["unlocked"].append(arc)
        if arc in history["locked"]:
            history["locked"].remove(arc)

    # - Arcs from paid feed (that are not in unlocked or locked) get added to "locked".
    for arc in paid_arcs_feed:
        if arc not in history["unlocked"] and arc not in history["locked"]:
            history["locked"].append(arc)

    # Deduplicate lists.
    history["unlocked"] = deduplicate(history["unlocked"])
    history["locked"] = deduplicate(history["locked"])
    save_history(history, history_file)

    # Determine the new locked arc.
    new_locked_arc = history["locked"][-1] if history["locked"] else None
    
    # Prevent duplicate announcements
    if new_locked_arc and new_locked_arc == history.get("last_announced", ""):
        print(f"✅ [{novel_title}] No new arc detected. Last announced: {history.get('last_announced', '')}")
        return
    
    # 🔽 Ensure last_announced is always updated
    if new_locked_arc:
        history["last_announced"] = new_locked_arc
        save_history(history, history_file)
        print(f"📌 Updated last_announced to: {new_locked_arc}")

    # Use the arc number from the new locked arc for the header.
    world_number = extract_arc_number(new_locked_arc)
    if world_number is None:
        world_number = len(history["unlocked"]) + len(history["locked"]) + 1

    # Build message sections.
    unlocked_section = "\n".join([format_stored_title(title) for title in history["unlocked"]])
    locked_section_lines = deduplicate([format_stored_title(title) for title in history["locked"]])
    if locked_section_lines:
        locked_section_lines[-1] = f"☛{locked_section_lines[-1]}"
    locked_section = "\n".join(locked_section_lines)

    # Construct the final Discord message.
    message = (
        f"{role_mention} <@&1329502951764525187>\n"
        "## :loudspeaker: NEW ARC ALERT˚ · .˚ ༘:butterfly:⋆｡˚\n"
        f"***《World {world_number}》is Live for***\n"
        f"### [{novel_title}]({novel_link}) <:Hehe:1329429547229122580>\n"
        "❀° ┄───────────────────────╮\n"
        "**`Unlocked 🔓`**\n"
        f"||{unlocked_section}||\n\n"
        "**`Locked 🔐`**\n"
        f"||{locked_section}||\n"
        "╰───────────────────────┄ °❀\n"
        f"> *Advance access is ready for you on {host}! :rose:*\n"
        "✎﹏﹏﹏﹏﹏﹏﹏﹏\n"
        f"-# React to the {custom_emoji} @ {discord_role_url} to get notified on updates and announcements~"
    )

    response = requests.post(discord_webhook, json={"content": message, "allowed_mentions": {"parse": []}, "flags": 4})
    if response.status_code == 204:
        print(f"✅ [{novel_title}] Sent notification for new arc: {new_locked_arc}")
    else:
        print(f"❌ [{novel_title}] Failed to send notification. Status Code: {response.status_code}")

# === MAIN PROCESS ===
with open("config.json", "r") as cf:
    config = json.load(cf)

for novel in config.get("novels", []):
    process_novel(novel)
