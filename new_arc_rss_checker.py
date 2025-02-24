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
        # Initialize with empty history if not present.
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
    if match:
        return f"**{match.group(1)}**{match.group(2)}"
    return f"**{title}**"

def extract_arc_number(title):
    match = re.search(r"【Arc\s*(\d+)】", title)
    if match:
        return int(match.group(1))
    return None

def deduplicate(lst):
    seen = set()
    result = []
    for item in lst:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

def nsfw_detected(feed_entries):
    """
    Check if any entry in the provided feed entries has a category that contains "nsfw".
    Returns True if found, otherwise False.
    """
    for entry in feed_entries:
        category = entry.get("category", "")
        if "nsfw" in category.lower():
            return True
    return False

def process_novel(novel):
    # Unpack novel configuration.
    free_feed_url = novel["free_feed"]
    paid_feed_url = novel["paid_feed"]
    # Use global webhook from environment (DISCORD_WEBHOOK)
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

    # Detect if NSFW is present in any free feed entry.
    if nsfw_detected(free_feed.entries):
        # Append additional role mention.
        role_mention = f"{role_mention} <@&1343352825811439616>"

    # Extract arc titles from feed entries that have " 001" in their nameextend.
    free_arcs_feed = [clean_feed_title(entry.get("nameextend", "").split(" 001")[0])
                       for entry in free_feed.entries if " 001" in entry.get("nameextend", "")]
    paid_arcs_feed = [clean_feed_title(entry.get("nameextend", "").split(" 001")[0])
                       for entry in paid_feed.entries if " 001" in entry.get("nameextend", "")]

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
    # (Assume the new locked arc is the last element in the locked list.)
    new_locked_arc = history["locked"][-1] if history["locked"] else None

    # Check the last announced arc stored in history.
    if new_locked_arc == history.get("last_announced", ""):
        print(f"✅ [{novel['name']}] No new arc detected. Last announced: {history.get('last_announced', '')}")
        return

    # Update last_announced in the same history file.
    history["last_announced"] = new_locked_arc
    save_history(history, history_file)

    # Use the arc number from the new locked arc for the header.
    world_number = extract_arc_number(new_locked_arc)
    if world_number is None:
        world_number = len(history["unlocked"]) + len(history["locked"]) + 1

    # Build the unlocked section.
    unlocked_section = "\n".join([format_stored_title(title) for title in history["unlocked"]])
    # Build the locked section.
    locked_section_lines = [format_stored_title(title) for title in history["locked"]]
    # Remove any duplicates.
    locked_section_lines = deduplicate(locked_section_lines)
    # Prefix only the new locked arc (assumed to be the last element) with the arrow.
    if locked_section_lines:
        locked_section_lines[-1] = f"☛{locked_section_lines[-1]}"
    locked_section = "\n".join(locked_section_lines)

    # Construct the final Discord message.
    message = (
        f"{role_mention}\n"
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

    data = {
        "content": message,
        "allowed_mentions": {"parse": []},
        "flags": 4  # Disable embeds
    }

    response = requests.post(discord_webhook, json=data)
    if response.status_code == 204:
        print(f"✅ [{novel['name']}] Sent notification for new arc: {new_locked_arc}")
    else:
        print(f"❌ [{novel['name']}] Failed to send notification. Status Code: {response.status_code}")

# === MAIN PROCESS ===
with open("config.json", "r") as cf:
    config = json.load(cf)

for novel in config.get("novels", []):
    process_novel(novel)
