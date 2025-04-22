import requests
import feedparser
import os
import json
import re

# === HELPER FUNCTIONS ===

def load_history(history_file):
    """Loads the novel's arc history from JSON file."""
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
            history.setdefault("last_announced", "")
            history.setdefault("last_extra_announced", 0)
        print(f"📂 Loaded history from {history_file}: {len(history['unlocked'])} unlocked, {len(history['locked'])} locked, last_announced={history['last_announced']}")
        return history
    else:
        print(f"📂 No history file found at {history_file}, starting fresh")
        return {"unlocked": [], "locked": [], "last_announced": "", "last_extra_announced": 0}

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

def parse_extras_info(chapter_count):
    """
    From a string like "1184 chapters + 8 extras" or 
    "950 chapters + 1 side story", return (total:int, raw_kw:str).
    If no extras/side‑stories, returns (0, None).
    """
    m = re.search(r"(\d+)\s*(extras?|side stories?)", chapter_count, re.IGNORECASE)
    if not m:
        return 0, None
    total = int(m.group(1))
    raw_kw = m.group(2).lower().rstrip('s')  # force singular: "side story"
    return total, raw_kw

def find_released_extras(paid_feed, raw_kw):
    """
    Scan <chaptername>, <nameextend>, <volume> for raw_kw + any number,
    return the set of numbers seen (as ints).
    """
    if not raw_kw:
        return set()
    pattern = re.compile(rf"(?i)\b{raw_kw}s?\b.*?(\d+)")
    seen = set()
    for e in paid_feed.entries:
        for field in ("chaptername","nameextend","volume"):
            val = e.get(field,"") or ""
            m = pattern.search(val)
            if m:
                seen.add(int(m.group(1)))
    return seen

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

def process_novel(novel):
    print(f"\n=== Processing novel: {novel['novel_title']} ===")
    # 0. parse feeds
    free_feed = feedparser.parse(novel["free_feed"])
    paid_feed = feedparser.parse(novel["paid_feed"])
    print(f"🌐 Fetched feeds: {len(free_feed.entries)} free entries, {len(paid_feed.entries)} paid entries")

    # 2. load history immediately after fetching feeds
    history = load_history(novel["history_file"])

    # --- Extras / Side‑Stories Announcement Logic (uses last_chapter) ---
    # 1) pull final‐chapter marker straight from config
    last_cfg = novel.get("last_chapter", "")
    m = re.match(r"(Extras?|Side Story|Side Stories?)\s+(\d+)", last_cfg, re.IGNORECASE)
    if m:
        final_type  = m.group(1).lower().rstrip("s")   # "extra" or "side story"
        final_index = int(m.group(2))
    else:
        final_type, final_index = None, 0

    # 2) see what’s actually dropped in the feed
    dropped_extras = find_released_extras(paid_feed, "extra")
    dropped_ss     = find_released_extras(paid_feed, "side story")
    max_ex = max(dropped_extras) if dropped_extras else 0
    max_ss = max(dropped_ss)     if dropped_ss     else 0

    # 3) only announce when something new appears
    last = history.get("last_extra_announced", 0)
    current = max(max_ex, max_ss)
    if current > last:
        # choose wording
        if final_type == "extra" and max_ex >= final_index:
            cm = "All extras just dropped"
        elif final_type == "side story" and max_ss >= final_index:
            cm = "All side stories just dropped"
        elif max_ex + max_ss == 1:
            cm = "The first of those extras just dropped"
        else:
            cm = "New extras just dropped"

        # build title/link line
        base = f"***[《{novel['novel_title']}》]({novel['novel_link']})***"
        # always show the configured totals
        m_ex = re.search(r"(\d+)\s*extras?", novel["chapter_count"], re.IGNORECASE)
        m_ss = re.search(r"(\d+)\s*side stories?", novel["chapter_count"], re.IGNORECASE)
        tot_ex = int(m_ex.group(1)) if m_ex else 0
        tot_ss = int(m_ss.group(1)) if m_ss else 0

        extra_label = "extra" if tot_ex == 1 else "extras"
        ss_label    = "side story" if tot_ss == 1 else "side stories"

        remaining = (
            f"{base} is almost at the very end — just "
            f"{tot_ex} {extra_label} and {tot_ss} {ss_label} left before we wrap up this journey for good."
        )

        msg = (
            f"{novel['role_mention']} | <@&1329502951764525187>\n"
            f"## :lotus:･ﾟ✧ NEW {'EXTRAS' if tot_ex>1 else 'EXTRA'} JUST DROPPED ✧ﾟ･:lotus:\n"
            f"{remaining}\n"
            f"{cm} in {novel['host']}'s advance access today. "
            "Thanks for sticking with this one ‘til the end. It means a lot. "
            "Please show your final love and support by leaving comments on the site~ :heart_hands:"
        )
        requests.post(
            os.getenv("DISCORD_WEBHOOK"),
            json={"content": msg, "flags": 4, "allowed_mentions": {"parse": ["roles"]}}
        )

        history["last_extra_announced"] = current
        save_history(history, novel["history_file"])
        commit_history_update(novel["history_file"])
    # --- End Extras Logic ---

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
        f"{novel['role_mention']} | <@&1329502951764525187>\n"
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
    resp = requests.post(
        os.getenv("DISCORD_WEBHOOK"),
        json={
            "content": message,
            "flags": 4,
            "allowed_mentions": { "parse": ["roles"] }
        }
    )
    if resp.status_code == 204:
        print(f"✅ Sent Discord notification for: {new_full}")
    else:
        print(f"❌ Failed to send Discord notification (status {resp.status_code})")
        
# === MAIN PROCESS ===
with open("config.json", "r", encoding="utf-8") as cf:
    config = json.load(cf)

for novel in config.get("novels", []):
    process_novel(novel)
