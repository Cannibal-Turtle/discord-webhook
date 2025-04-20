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
    """Saves the novel's arc history to JSON file with proper encoding."""
    print(f"📂 Checking before saving: {history_file}")

    # Save JSON with `ensure_ascii=False` to keep characters like 【】 readable
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)  # ✅ Fixes Unicode issue

    print(f"✅ Successfully updated history file: {history_file}")

def commit_history_update(history_file):
    """Commits and pushes the updated history file to GitHub."""
    print(f"📌 Committing changes for {history_file}...")

    os.system("git config --global user.name 'GitHub Actions'")
    os.system("git config --global user.email 'actions@github.com'")

    # Check if there are any changes
    os.system("git status")  # Debugging: See what Git detects

    # Ensure the file is staged
    os.system(f"git add {history_file}")

    # Check if there are actually any changes before committing
    changes_detected = os.system("git diff --staged --quiet")  # Exits 1 if changes exist

    if changes_detected != 0:
        os.system(f"git commit -m 'Auto-update: {history_file}'")
        print(f"✅ Committed changes for {history_file}")
    else:
        print(f"⚠️ No changes detected in {history_file}, skipping commit.")

    # Attempt to push, with retry logic in case of failure
    push_status = os.system("git push origin main")

    if push_status != 0:
        print("❌ Git push failed. Trying again with force...")
        os.system("git push origin main --force")  # Force push if necessary

def clean_feed_title(raw_title):
    """Removes extra characters from feed titles."""
    return raw_title.replace("*", "").strip()

def format_stored_title(title):
    """Formats arc titles for Discord messages."""
    match = re.match(r"(【Arc\s+\d+】)\s*(.*)", title)
    return f"**{match.group(1)}**{match.group(2)}" if match else f"**{title}**"

def extract_arc_number_from_suffix(nameextend):
    if nameextend.endswith(" 001"):
        return 1
    m = re.search(r"\((\d+)\)$", nameextend)
    if m:
        return int(m.group(1))
    return None

def next_arc_number(history):
    # 1) Try parsing last_announced
    last = history.get("last_announced", "")
    m = re.search(r"【Arc\s*(\d+)】", last)
    if m:
        return int(m.group(1)) + 1

    # 2) Otherwise scan unlocked+locked for the max Arc n
    nums = []
    for section in ("unlocked","locked"):
        for title in history[section]:
            m = re.search(r"【Arc\s*(\d+)】", title)
            if m:
                nums.append(int(m.group(1)))
    return max(nums, default=0) + 1

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
    # first, actually fetch the RSS feeds
    free_feed = feedparser.parse(novel["free_feed"])
    paid_feed = feedparser.parse(novel["paid_feed"])

    # helper: volume‑first / nameextend‑fallback
    def extract_arcs(feed):
        arcs = []
        for entry in feed.entries:
            vol        = entry.get("volume","").strip()
            raw        = entry.get("nameextend","")
            has_marker = "001" in raw or "(1)" in raw
            if vol:
                if has_marker:
                    arcs.append({"title": vol, "raw": raw})
            else:
                if has_marker:
                    title = extract_arc_title(raw)
                    arcs.append({"title": title, "raw": raw})
        return arcs

    free_arcs_feed = extract_arcs(free_feed)
    paid_arcs_feed = extract_arcs(paid_feed)
    
    # Detect NSFW flag
    role_mention = novel["role_mention"]
    if nsfw_detected(free_feed.entries, novel["novel_title"]):
        role_mention = f"{role_mention} <@&1329502951764525187> <@&1343352825811439616>"

    history = load_history(novel["history_file"])
    for item in free_arcs_feed:
        t = item["title"]
        if t not in history["unlocked"]:
            history["unlocked"].append(t)
        if t in history["locked"]:
            history["locked"].remove(t)
    for item in paid_arcs_feed:
        t = item["title"]
        if t not in history["unlocked"] and t not in history["locked"]:
            history["locked"].append(t)
    history["unlocked"] = deduplicate(history["unlocked"])
    history["locked"]   = deduplicate(history["locked"])
    save_history(history, novel["history_file"])

    # Detect new locked arc
    new_locked_arc = history["locked"][-1] if history["locked"] else None
    if not new_locked_arc or new_locked_arc == history["last_announced"]:
        return

    history["last_announced"] = new_locked_arc
    save_history(history, novel["history_file"])
    commit_history_update(novel["history_file"])
        
    world_number = next_arc_number(history)

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
