import requests
import feedparser
import os
import json
import re

# === HELPER FUNCTIONS ===
def load_history(history_file):
    """Loads the novel's arc history from JSON file."""
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            return json.load(f)
    else:
        return {"unlocked": [], "locked": [], "last_announced": ""}

def save_history(history, history_file):
    """Saves the novel's arc history to JSON file and verifies the update."""
    print(f"📂 Checking before saving: {history_file}")
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            print(f"🔍 Before Update: {json.load(f)}")  # Print old content

    with open(history_file, "w") as f:
        json.dump(history, f, indent=4)

    print(f"✅ Successfully updated history file: {history_file}")

    with open(history_file, "r") as f:
        print(f"📂 After Update: {json.load(f)}")  # Print updated content
        
def commit_history_update(history_file):
    """Commits and pushes the updated history file to GitHub."""
    os.system(f"git add {history_file}")
    os.system(f"git commit -m 'Auto-update: {history_file}' || echo 'No changes to commit'")
    os.system("git push origin main || echo 'Push failed, check permissions'")

def clean_feed_title(raw_title):
    """Removes extra characters from feed titles."""
    return raw_title.replace("*", "").strip()

def format_stored_title(title):
    """Formats arc titles for Discord messages."""
    match = re.match(r"(【Arc\s+\d+】)\s*(.*)", title)
    return f"**{match.group(1)}**{match.group(2)}" if match else f"**{title}**"

def extract_arc_number(title):
    """Extracts arc number from title."""
    match = re.search(r"【Arc\s*(\d+)】", title)
    return int(match.group(1)) if match else None

def deduplicate(lst):
    """Removes duplicates while preserving order."""
    seen = set()
    return [x for x in lst if not (x in seen or seen.add(x))]

def nsfw_detected(feed_entries, novel_title):
    """Checks if NSFW category exists for this novel."""
    for entry in feed_entries:
        if novel_title.lower() in entry.get("title", "").lower():
            if "nsfw" in entry.get("category", "").lower():
                return True
    return False

def extract_arc_title(nameextend):
    """Extracts arc title by removing unwanted suffixes like ' 001' or '(1)'."""
    for suffix in [" 001", "(1)"]:
        if suffix in nameextend:
            return clean_feed_title(nameextend.split(suffix)[0])
    return clean_feed_title(nameextend)

# === PROCESS NOVEL FUNCTION ===
def process_novel(novel):
    """Processes a novel, updates history, and sends a Discord message if a new arc is detected."""
    free_feed = feedparser.parse(novel["free_feed"])
    paid_feed = feedparser.parse(novel["paid_feed"])
    
    # Detect NSFW flag
    role_mention = novel["role_mention"]
    if nsfw_detected(free_feed.entries, novel["novel_title"]):
        role_mention = f"{role_mention} <@&1329502951764525187> <@&1343352825811439616>"

    # Extract arcs
    free_arcs_feed = [extract_arc_title(entry.get("nameextend", "")) 
                      for entry in free_feed.entries if " 001" in entry.get("nameextend", "") or "(1)" in entry.get("nameextend", "")]
    
    paid_arcs_feed = [extract_arc_title(entry.get("nameextend", "")) 
                      for entry in paid_feed.entries if " 001" in entry.get("nameextend", "") or "(1)" in entry.get("nameextend", "")]

    # Load novel history
    history = load_history(novel["history_file"])

    # Update history
    for arc in free_arcs_feed:
        if arc not in history["unlocked"]:
            history["unlocked"].append(arc)
        if arc in history["locked"]:
            history["locked"].remove(arc)

    for arc in paid_arcs_feed:
        if arc not in history["unlocked"] and arc not in history["locked"]:
            history["locked"].append(arc)

    history["unlocked"] = deduplicate(history["unlocked"])
    history["locked"] = deduplicate(history["locked"])
    save_history(history, novel["history_file"])

    # Detect new locked arc
    new_locked_arc = history["locked"][-1] if history["locked"] else None

    # Prevent duplicate announcements
    if new_locked_arc and new_locked_arc == history.get("last_announced", ""):
        print(f"✅ [{novel['novel_title']}] No new arc detected. Last announced: {history.get('last_announced', '')}")
        return
    
    # 🔽 Ensure last_announced is always updated
    if new_locked_arc:
        history["last_announced"] = new_locked_arc
        save_history(history, novel["history_file"])
        print(f"📌 Updated last_announced to: {new_locked_arc}")

    # Use the arc number from the new locked arc for the header.
    world_number = extract_arc_number(new_locked_arc) or len(history["unlocked"]) + len(history["locked"]) + 1

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
        f"### [{novel['novel_title']}]({novel['novel_link']}) <:Hehe:1329429547229122580>\n"
        "❀° ┄───────────────────────╮\n"
        "**`Unlocked 🔓`**\n"
        f"||{unlocked_section}||\n\n"
        "**`Locked 🔐`**\n"
        f"||{locked_section}||\n"
        "╰───────────────────────┄ °❀\n"
        f"> *Advance access is ready for you on {novel['host']}! :rose:*\n"
        "✎﹏﹏﹏﹏﹏﹏﹏﹏\n"
        f"-# React to the {novel['custom_emoji']} @ {novel['discord_role_url']} to get notified on updates and announcements~"
    )

    response = requests.post(os.getenv("DISCORD_WEBHOOK"), json={"content": message, "allowed_mentions": {"parse": []}, "flags": 4})
    if response.status_code == 204:
        print(f"✅ [{novel['novel_title']}] Sent notification for new arc: {new_locked_arc}")
    else:
        print(f"❌ [{novel['novel_title']}] Failed to send notification. Status Code: {response.status_code}")

# === MAIN PROCESS ===
with open("config.json", "r") as cf:
    config = json.load(cf)

for novel in config.get("novels", []):
    process_novel(novel)
