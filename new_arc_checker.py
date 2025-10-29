import requests
import feedparser
import os
import json
import re
import sys
from novel_mappings import HOSTING_SITE_DATA, get_nsfw_novels

# ─── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID     = os.environ["DISCORD_CHANNEL_ID"]
ONGOING_ROLE   = "<@&1329502951764525187>"
NSFW_ROLE_ID   = "<@&1343352825811439616>"
# ────────────────────────────────────────────────────────────────────────────────

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
    resp = requests.post(url, headers=headers, json=payload)
    if not resp.ok:
        # print the Discord error payload so you know exactly why it’s 400
        print(f"⚠️ Bot error {resp.status_code}: {resp.text}")
    resp.raise_for_status()

def load_history(history_file):
    """
    Loads the novel's arc history from JSON file.
    If the file is missing OR it's empty / invalid JSON,
    we fall back to a fresh structure so the run doesn't die.
    """
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            raw = f.read().strip()

        if not raw:
            # file exists but is blank
            print(f"📂 {history_file} is empty, initializing fresh history")
            return {"unlocked": [], "locked": [], "last_announced": ""}

        try:
            history = json.loads(raw)
        except json.JSONDecodeError:
            # file exists but has garbage / half-written JSON
            print(f"📂 {history_file} was invalid JSON, re-initializing fresh history")
            history = {"unlocked": [], "locked": [], "last_announced": ""}

        # make sure keys exist
        history.setdefault("unlocked", [])
        history.setdefault("locked", [])
        history.setdefault("last_announced", "")

        print(
            f"📂 Loaded history from {history_file}: "
            f"{len(history['unlocked'])} unlocked, "
            f"{len(history['locked'])} locked, "
            f"last_announced={history['last_announced']}"
        )
        return history

    # no file at all -> brand new novel
    print(f"📂 No history file found at {history_file}, starting fresh")
    return {"unlocked": [], "locked": [], "last_announced": ""}

def save_history(history, history_file):
    """Saves the novel's arc history to JSON file with proper encoding."""
    print(
        f"📂 Saving history to {history_file} "
        f"(unlocked={len(history['unlocked'])}, "
        f"locked={len(history['locked'])}, "
        f"last_announced={history['last_announced']})"
    )
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
      "【Arc 22】Foo"    → "Foo"
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

# ─── DIGIT EMOJI MAP & HELPER ──────────────────────────────────────────────────
DIGIT_EMOJI = {
    '0': '<:7987_zero_emj_png:1368137498496335902>',
    '1': '<:5849_one_emj_png:1368137451801149510>',
    '2': '<:4751_two_emj_png:1368137429369753742>',
    '3': '<:5286_three_emj_png:1368137406523637811>',
    '4': '<:4477_four_emj_png:1368137382813106196>',
    '5': '<:3867_five_emj_png:1368137358800715806>',
    '6': '<:8923_six_emj_png:1368137333886550098>',
    '7': '<:4380_seven_emj_png:1368137314240303165>',
    '8': '<:9891_eight_emj_png:1368137290517581995>',
    '9': '<:1898_nine_emj_png:1368137143196717107>',
}

def number_to_emoji(n: int) -> str:
    """
    Convert an integer to its emoji-digit representation.
    e.g. 24 -> DIGIT_EMOJI['2'] + DIGIT_EMOJI['4']
    """
    return ''.join(DIGIT_EMOJI[d] for d in str(n))

# ──────────────────────────────────────────────────────────────────────────────
# === PROCESS NOVEL FUNCTION ===

def process_arc(novel):
    print(f"\n=== Processing novel: {novel['novel_title']} ===")

    # 0. Fetch feeds for this novel
    free_feed = feedparser.parse(novel["free_feed"])
    paid_feed = feedparser.parse(novel["paid_feed"])
    print(f"🌐 Fetched feeds: {len(free_feed.entries)} free entries, {len(paid_feed.entries)} paid entries")

    # 1. NSFW check
    is_nsfw = (
        novel["novel_title"] in get_nsfw_novels()
        or nsfw_detected(free_feed.entries + paid_feed.entries, novel["novel_title"])
    )
    print(f"🕵️ is_nsfw={is_nsfw} for {novel['novel_title']}")

    base_mention = novel["role_mention"] + (f" | {NSFW_ROLE_ID}" if is_nsfw else "")

    history_file = novel.get("history_file")
    if not history_file:
        print(f"⚠️ No history_file configured for '{novel['novel_title']}', skipping arcs.")
        return

    # 2. Load history
    history = load_history(history_file)

    # snapshot BEFORE we mutate history so we know if this is truly first-ever arc
    had_any_locked_before    = bool(history["locked"])
    had_any_unlocked_before  = bool(history["unlocked"])

    # Helper: does string look like a "new arc start" marker
    # Helper: does this entry look like the FIRST chapter of a new arc/world?
    def is_new_marker(raw: str):
        """
        Legacy Dragonholic markers:
         - ends with '001'
         - ends with '(1)'
         - ends with '.1'
         (We also allow trailing **** now, for safety.)
        """
        if not raw:
            return False
        raw = raw.strip()
        return bool(
            re.search(r"(001|\(1\)|\.\s*1)(\*+)?\s*$", raw)
        )

    def looks_like_arc_start(raw_vol: str, raw_chap: str, raw_extend: str):
        """
        Decide if this RSS entry is the 'new arc/world just started' chapter.
        """
        rv   = (raw_vol    or "").strip()   # e.g. "Arc 2: ..."
        rc   = (raw_chap   or "").strip()   # e.g. "Chapter 50"
        rext = (raw_extend or "").strip()   # e.g. "***2.1***"
    
        # 1) Dragonholic / legacy markers: "001", "(1)", ".1"
        if is_new_marker(rext) or is_new_marker(rc):
            return True
    
        # 2) Mistmint pattern: local index "X.Y" (maybe wrapped in ***)
        if re.match(r"^\**\s*\d+\.\d+\s*\**$", rext):
            # sanity: volume should look like Arc/World/Plane/Story/Volume/Vol/V <num>
            if re.match(r"(?i)^(arc|world|plane|story|volume|vol|v)\s*\d+", rv):
                return True
    
        # 3) Soft fallback:
        #    Volume looks like Arc/World/... <num>, BUT rext didn't carry a first-subchapter marker
        if re.match(r"(?i)^(arc|world|plane|story|volume|vol|v)\s*\d+", rv):
            if not is_new_marker(rext) and not re.match(r"^\**\s*\d+\.\d+\s*\**$", rext):
                return True
    
        return False

    def extract_new_bases(feed, current_title):
        bases = []
        for e in feed.entries:
            # only consider entries that actually belong to THIS novel
            entry_title = (e.get("title") or "").strip()
            if entry_title != current_title:
                continue

            raw_vol    = (e.get("volume", "") or "").replace("\u00A0", " ").strip()
            raw_extend = (e.get("nameextend", "") or "").replace("\u00A0", " ").strip()
            raw_chap   = (e.get("chaptername", "") or "").replace("\u00A0", " ").strip()

            # is this entry the START of an arc/world?
            if not looks_like_arc_start(raw_vol, raw_chap, raw_extend):
                continue

            # Pick a base name to represent the arc/world:
            # prefer volume ("Arc 1: Tycoon Boss Gong × ...")
            if raw_vol:
                base = clean_feed_title(raw_vol)
            elif raw_extend:
                base = extract_arc_title(raw_extend)
            else:
                base = raw_chap

            # Remove leading numbering like "Arc 3: ", "World 7 - ", etc.
            base = strip_any_number_prefix(base)

            bases.append(base)

        return bases

    
    free_new = extract_new_bases(free_feed, novel["novel_title"])
    paid_new = extract_new_bases(paid_feed, novel["novel_title"])
    print(f"🔍 Detected {len(free_new)} new free arcs, {len(paid_new)} new paid arcs")

    # 3. Update history with free-start arcs / paid-start arcs
    free_created_new_arc = False
    paid_created_new_arc = False

    # --- 3A. Handle free arcs
    for base in free_new:
        matched_locked = False

        # Case: arc was previously locked, now unlocked
        for full in history["locked"][:]:
            if full.endswith(base):
                matched_locked = True
                history["locked"].remove(full)
                if full not in history["unlocked"]:
                    history["unlocked"].append(full)
                    print(f"🔓 Unlocked arc: {full}")
                break

        # Case: completely new arc that STARTED free (never in locked)
        if not matched_locked:
            seen_bases = [
                re.sub(r"^【Arc\s*\d+】", "", t)
                for t in (history["unlocked"] + history["locked"])
            ]
            if base not in seen_bases:
                n = next_arc_number(history)
                full = f"【Arc {n}】{base}"
                history["unlocked"].append(full)
                free_created_new_arc = True
                print(f"🌿 Registered brand-new free arc: {full}")

    # --- 3B. Handle paid arcs
    seen_bases_after_free = [
        re.sub(r"^【Arc\s*\d+】", "", f)
        for f in (history["unlocked"] + history["locked"])
    ]
    for base in paid_new:
        if base not in seen_bases_after_free:
            n = next_arc_number(history)
            full = f"【Arc {n}】{base}"
            history["locked"].append(full)
            paid_created_new_arc = True
            print(f"🔐 New locked arc: {full}")

    # 4. Deduplicate lists
    history["unlocked"] = deduplicate(history["unlocked"])
    history["locked"]   = deduplicate(history["locked"])

    # --- NEW: unified first-run bootstrap guard ---
    # If history was empty before this run, don't announce anything even if both
    # free and paid created entries. Just save numbering and exit.
    if (not had_any_locked_before and not had_any_unlocked_before
        and (free_created_new_arc or paid_created_new_arc)):
        print("🌱 First run detected (history was empty). Storing arc numbering only; no Discord ping.")
        save_history(history, novel["history_file"])
        commit_history_update(novel["history_file"])
        return
            
    # 5. Figure out what (if anything) to announce

    # A) Special case 1: first-ever arc started FREE and nothing locked
    scenario_first_arc_free_only = (
        free_created_new_arc
        and not paid_created_new_arc
        and not history["locked"]  # still zero locked arcs
    )

    if scenario_first_arc_free_only:
        print("🌱 First arc started free. Saving numbering to history, no Discord ping.")
        save_history(history, novel["history_file"])
        commit_history_update(novel["history_file"])
        return

    # B) Special case 2: first-ever arc started PAID ONLY
    scenario_first_arc_paid_only = (
        paid_created_new_arc
        and not free_created_new_arc
        and not had_any_locked_before
        and not had_any_unlocked_before
    )

    if scenario_first_arc_paid_only:
        print("💸 First arc started paid-only. Saving numbering to history, no Discord ping.")
        # Don't touch last_announced.
        save_history(history, novel["history_file"])
        commit_history_update(novel["history_file"])
        return

    # After those two bootstraps, continue like normal.

    # If we have no locked arcs at all (nothing advance-only to hype), stop.
    if not history["locked"]:
        print("ℹ️ No locked arcs exist. Nothing to announce.")
        return

    new_full = history["locked"][-1]  # newest locked arc title, e.g. "【Arc 5】..."
    last_announced = history.get("last_announced", "")

    # If we've already announced this exact locked arc, we're done.
    if new_full == last_announced:
        print(f"✅ Already announced latest locked arc: {new_full}")
        return

    # 6. Build display strings with UPDATED history
    world_number = extract_arc_number(new_full)
    world_emoji  = number_to_emoji(world_number) if world_number is not None else ""

    # Build pretty text lists for unlocked / locked arcs
    unlocked_list = history["unlocked"]
    locked_list   = history["locked"]

    has_unlocked = bool(unlocked_list)

    unlocked_md = "\n".join(format_stored_title(t) for t in unlocked_list)

    locked_lines = [format_stored_title(t) for t in locked_list]
    locked_lines = deduplicate(locked_lines)
    if locked_lines:
        # mark the newest locked arc with a pink arrow
        locked_lines[-1] = f"<a:9410pinkarrow:1368139217556996117>{locked_lines[-1]}"
    locked_md = "\n".join(locked_lines)

    # 7. Build the Discord messages

    content_header = (
        f"{base_mention} | {ONGOING_ROLE} <a:Crown:1365575414550106154>\n"
        "## <a:announcement:1365566215975731274> NEW ARC ALERT "
        "<a:pinksparkles:1365566023201198161>"
        "<a:Butterfly:1365572264774471700>"
        "<a:pinksparkles:1365566023201198161>\n"
        f"***<:babypinkarrowleft:1365566594503147550>"
        f"<:world_01:1368202193038999562>"
        f"<:world_02:1368202204468613162> {world_emoji}"
        f"<:babypinkarrowright:1365566635838275595>is Live for*** "
        "<a:pinkloading:1365566815736172637>\n"
        f"### [{novel['novel_title']}]({novel['novel_link']}) "
        "<a:Turtle_Police:1365223650466205738>\n"
        "❀° ┄───────────────────────╮"
    )

    # Only build embed_unlocked if there's actually at least one unlocked arc
    if has_unlocked:
        embed_unlocked = {
            "description": unlocked_md,
            "color": 0xFFF9BF
        }
    else:
        embed_unlocked = None  # sentinel

    embed_locked = {
        "description": f"||{locked_md if locked_md else 'None'}||",
        "color": 0xA87676
    }

    footer_and_react = (
        "╰───────────────────────┄ °❀\n"
        f"> *Advance access is ready for you on {novel['host']}! "
        "<a:holo_diamond:1365566087277711430>*\n"
        + "<:pinkdiamond_border:1365575603734183936>" * 6 + "\n"
        "-# React to the "
        f"{novel['custom_emoji']} @ {novel['discord_role_url']} "
        "to get notified on updates and announcements "
        "<a:LoveLetter:1365575475841339435>"
    )

    # 8. Send all Discord messages
    header_ok = False
    try:
        r1 = requests.post(
            f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages",
            headers={
                "Authorization": f"Bot {BOT_TOKEN}",
                "Content-Type":  "application/json"
            },
            json={
                "content": content_header,
                "allowed_mentions": {"parse": ["roles"]},
                "flags": 4
            }
        )
        if r1.ok:
            header_ok = True
        r1.raise_for_status()
        print(f"✅ Header sent for: {new_full}")
    except requests.RequestException as e:
        print(f"⚠️ Header send failed: {e}", file=sys.stderr)

    # Send "Unlocked 🔓" block only if we actually have unlocked arcs
    if has_unlocked and embed_unlocked is not None:
        try:
            requests.post(
                f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages",
                headers={
                    "Authorization": f"Bot {BOT_TOKEN}",
                    "Content-Type":  "application/json"
                },
                json={
                    "content": "<a:5693pinkwings:1368138669004820500> `Unlocked 🔓` <a:5046_bounce_pink:1368138460027813888>",
                    "embeds": [embed_unlocked],
                    "allowed_mentions": {"parse": ["roles"]},
                }
            ).raise_for_status()
            print(f"✅ Unlocked embed sent for: {new_full}")
        except requests.RequestException as e:
            print(f"⚠️ Unlocked send failed: {e}", file=sys.stderr)
    else:
        print("ℹ️ Skipping Unlocked block (no unlocked arcs).")

    # Locked block (always send, because this is the new arc hype)
    try:
        requests.post(
            f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages",
            headers={
                "Authorization": f"Bot {BOT_TOKEN}",
                "Content-Type":  "application/json"
            },
            json={
                "content": "<a:5693pinkwings:1368138669004820500> `Locked 🔐` <a:5046_bounce_pink:1368138460027813888>",
                "embeds": [embed_locked],
                "allowed_mentions": {"parse": ["roles"]},
            }
        ).raise_for_status()
        print(f"✅ Locked embed sent for: {new_full}")
    except requests.RequestException as e:
        print(f"⚠️ Locked send failed: {e}", file=sys.stderr)

    # Footer / react block
    try:
        requests.post(
            f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages",
            headers={
                "Authorization": f"Bot {BOT_TOKEN}",
                "Content-Type":  "application/json"
            },
            json={
                "content": footer_and_react,
                "allowed_mentions": {"parse": ["roles"]},
                "flags": 4
            }
        ).raise_for_status()
        print(f"✅ Footer/react sent for: {new_full}")
    except requests.RequestException as e:
        print(f"⚠️ Footer/react send failed: {e}", file=sys.stderr)

    # 9. Mark it announced, save, commit.
    if header_ok:
        history["last_announced"] = new_full
        save_history(history, novel["history_file"])
        commit_history_update(novel["history_file"])
        print(f"📌 Finished announcing and recorded last_announced = {new_full}")
    else:
        print("⚠️ Did not update last_announced because header send failed.")


# === LOAD & RUN ===
if __name__ == "__main__":
    for host, host_data in HOSTING_SITE_DATA.items():
        for title, d in host_data.get("novels", {}).items():
            # Only process novels that have both feeds configured
            if not d.get("free_feed") or not d.get("paid_feed"):
                continue

            novel = {
                "novel_title":      title,
                "role_mention":     d.get("discord_role_id", ""),
                "host":             host,
                "free_feed":        d["free_feed"],
                "paid_feed":        d["paid_feed"],
                "novel_link":       d.get("novel_url", ""),
                "custom_emoji":     d.get("custom_emoji", ""),
                "discord_role_url": d.get("discord_role_url", ""),
                "history_file":     d.get("history_file", "")
            }
            process_arc(novel)
