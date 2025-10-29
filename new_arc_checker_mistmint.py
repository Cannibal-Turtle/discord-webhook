#!/usr/bin/env python3
"""
new_arc_checker_mistmint.py

Manual arc announcer for Mistmint Haven.

Why this exists:
- Mistmint hides chapter lists and premium/advance releases behind JS + auth,
  so our normal scraper in new_arc_checker.py can't "see" new arcs.
- BUT you (hi 💖) know the arc boundaries and when a new world/arc goes live
  in advance/premium.
- You keep those arcs in a YAML file (arc_schedule.yaml) with status:
    - "locked"   = currently premium/advance-only
    - "unlocked" = already public/free
- This script compares that YAML vs the saved history JSON
  (tdlbkgc_history.json from HOSTING_SITE_DATA["Mistmint Haven"][novel]["history_file"]).

If it detects a brand-new locked arc that has never been seen before,
it posts the usual NEW ARC ALERT Discord sequence:
  - header block w/ roles + world number emoji
  - Unlocked 🔓 embed (free arcs list)
  - Locked 🔐 embed (advance arcs list, pink arrow on the newest one)
  - footer block telling people how to get the role

Then it updates the history file and commits it back to the repo
(using git, exactly like new_arc_checker.py does).

If nothing new is locked, it just syncs the history file to match YAML
and commits (no Discord spam).

Env vars required (same as the other bots):
  DISCORD_BOT_TOKEN
  DISCORD_CHANNEL_ID
"""

import os
import json
import re
import sys
import subprocess
import requests
import yaml  # PyYAML
from typing import List, Dict, Any

# pull shared data from your mapping package
from novel_mappings import HOSTING_SITE_DATA, get_nsfw_novels

# ─── CONFIG / CONSTANTS ──────────────────────────────────────────────

BOT_TOKEN      = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID     = os.environ["DISCORD_CHANNEL_ID"]

# same global roles / IDs you're already using in new_arc_checker.py
ONGOING_ROLE   = "<@&1329502951764525187>"
NSFW_ROLE_ID   = "<@&1343352825811439616>"

# which YAML file maps to which novel
# (path is relative to this repo root as checked out in Actions)
ARC_YAML_MAP = {
    "[Quick Transmigration] The Delicate Little Beauty Keeps Getting Caught": "arc_schedule.yaml",
}

# digit emojis for "world number" display
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

# ─── SMALL HELPERS ──────────────────────────────────────────────────

def number_to_emoji(n: int) -> str:
    """Turn 24 -> '₂₄' but with your custom <:2><:4> style."""
    return "".join(DIGIT_EMOJI[d] for d in str(n))

def load_history(path: str) -> Dict[str, Any]:
    """
    History JSON:
    {
      "unlocked": ["【Arc 1】Foo", ...],
      "locked":   ["【Arc 20】Tentacled Alien ...", ...],
      "last_announced": "【Arc 20】Tentacled Alien ...",
    }
    """
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("unlocked", [])
        data.setdefault("locked", [])
        data.setdefault("last_announced", "")
        return data
    return {"unlocked": [], "locked": [], "last_announced": ""}

def save_history(data: Dict[str, Any], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def commit_history_update(history_file: str):
    """
    Commit + push the updated history file (like your existing script).
    """
    print(f"📌 Committing changes for {history_file}...")

    subprocess.run(["git", "config", "--global", "user.name", "GitHub Actions"], check=False)
    subprocess.run(["git", "config", "--global", "user.email", "actions@github.com"], check=False)

    subprocess.run(["git", "status"], check=False)
    subprocess.run(["git", "add", history_file], check=False)

    diff_rc = subprocess.run(["git", "diff", "--staged", "--quiet"]).returncode
    if diff_rc != 0:
        subprocess.run(["git", "commit", "-m", f"Auto-update: {history_file}"], check=False)
        print(f"✅ Committed changes for {history_file}")
    else:
        print(f"⚠️ No changes detected in {history_file}, skipping commit.")

    push_rc = subprocess.run(["git", "push", "origin", "main"]).returncode
    if push_rc != 0:
        print("❌ Git push failed. Retrying with --force ...")
        subprocess.run(["git", "push", "origin", "main", "--force"], check=False)

def extract_arc_number(full_title: str) -> int:
    """
    "【Arc 20】 Tentacled Alien Gong × Passerby Doctor Shou" -> 20
    """
    m = re.search(r"【Arc\s*(\d+)】", full_title)
    return int(m.group(1)) if m else 0

def format_stored_title(full_title: str) -> str:
    """
    Make the arc prefix bold for embeds:
    "【Arc 5】 Some Title" -> "**【Arc 5】**Some Title"
    """
    m = re.match(r"(【Arc\s+\d+】)\s*(.*)", full_title)
    if m:
        return f"**{m.group(1)}**{m.group(2)}"
    return f"**{full_title}**"

def deduplicate(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def post_discord_message(content: str,
                         embeds: List[dict] | None = None,
                         suppress_embeds: bool = False):
    """
    Send a Discord message in-channel using the bot token.
    allowed_mentions.parse=["roles"] so your role IDs ping correctly.
    suppress_embeds -> sets flags=4 like your other code.
    """
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type":  "application/json"
    }
    payload = {
        "content": content,
        "allowed_mentions": {"parse": ["roles"]},
    }
    if embeds:
        payload["embeds"] = embeds
    if suppress_embeds:
        payload["flags"] = 4  # SUPPRESS_EMBEDS

    resp = requests.post(url, headers=headers, json=payload)
    if not resp.ok:
        print(f"⚠️ Discord error {resp.status_code}: {resp.text}", file=sys.stderr)
    resp.raise_for_status()
    return True

# ─── YAML PARSER ────────────────────────────────────────────────────

def load_yaml_arcs(yaml_path: str):
    """
    Read arc_schedule.yaml:

    novel: "[Quick Transmigration] The Delicate Little Beauty Keeps Getting Caught"
    host: "Mistmint Haven"

    arcs:
      - num: 20
        title: "Tentacled Alien Gong × Passerby Doctor Shou"
        start_chapter: 701
        end_chapter: 734
        status: locked      # or unlocked

    Returns:
        unlocked_full_titles: ["【Arc 1】Tycoon Boss ...", ...]  (sorted by num)
        locked_full_titles:   ["【Arc 20】Tentacled Alien ...", ...]  (sorted by num)
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    arcs = data.get("arcs", [])
    unlocked = []
    locked   = []

    for arc in arcs:
        num    = arc.get("num")
        title  = arc.get("title", "").strip()
        status = (arc.get("status") or "").strip().lower()

        if num is None or not title:
            continue

        full = f"【Arc {num}】{title}".strip()

        if status == "unlocked":
            unlocked.append((num, full))
        elif status == "locked":
            locked.append((num, full))
        # else ignore (no status / unknown)

    unlocked.sort(key=lambda x: x[0])
    locked.sort(key=lambda x: x[0])

    unlocked_titles = [ft for (_n, ft) in unlocked]
    locked_titles   = [ft for (_n, ft) in locked]

    return unlocked_titles, locked_titles

# ─── CORE LOGIC ─────────────────────────────────────────────────────

def process_mistmint_novel(novel: Dict[str, str], yaml_path: str):
    """
    This does the "is there a new premium arc?" check
    and (optionally) blasts Discord.

    novel dict should look like:
      {
        "novel_title":      "...",
        "role_mention":     "<@&...>",      # series role
        "host":             "Mistmint Haven",
        "novel_link":       "https://...",
        "custom_emoji":     "<:...>",
        "discord_role_url": "https://discord.com/channels/.../...",
        "history_file":     "tdlbkgc_history.json",
      }
    """

    print(f"\n=== Processing Mistmint novel: {novel['novel_title']} ===")
    hist_path = novel["history_file"]

    # 1. previous run state (JSON)
    prev_history = load_history(hist_path)
    prev_locked_set   = set(prev_history.get("locked", []))
    prev_unlocked_set = set(prev_history.get("unlocked", []))
    prev_last_ann     = prev_history.get("last_announced", "")

    # 2. YAML truth from arc_schedule.yaml
    yaml_unlocked, yaml_locked = load_yaml_arcs(yaml_path)
    print(f"YAML says unlocked={len(yaml_unlocked)}, locked={len(yaml_locked)}")

    # 3. figure out what's BRAND NEW premium
    newly_locked = [
        full for full in yaml_locked
        if full not in prev_locked_set and full not in prev_unlocked_set
    ]
    print(f"Detected {len(newly_locked)} brand-new locked arcs: {newly_locked}")

    # 4. build the new history snapshot we want to store
    new_history = {
        "unlocked": yaml_unlocked[:],
        "locked":   yaml_locked[:],
        "last_announced": prev_last_ann
    }

    # "bootstrap mode": first-ever run → don't spam old arcs
    bootstrap_mode = (
        len(prev_history.get("locked", [])) == 0 and
        len(prev_history.get("unlocked", [])) == 0 and
        prev_last_ann.strip() == ""
    )

    if bootstrap_mode:
        print("🌱 Bootstrap sync only (first run). No Discord announcement.")
        save_history(new_history, hist_path)
        commit_history_update(hist_path)
        return

    # if nothing new is in locked, just sync history and quit quietly
    if not newly_locked:
        print("ℹ️ No new locked arcs to announce. Syncing history + exiting.")
        save_history(new_history, hist_path)
        commit_history_update(hist_path)
        return

    # 5. we DO have a new premium arc → announce it
    def arc_num(full_title: str) -> int:
        return extract_arc_number(full_title)

    announce_full = max(newly_locked, key=arc_num)
    world_number  = extract_arc_number(announce_full)
    world_emoji   = number_to_emoji(world_number) if world_number else ""

    # nsfw role logic: series role + nsfw role if flagged
    is_nsfw = novel["novel_title"] in get_nsfw_novels()
    base_mention = novel["role_mention"] + (f" | {NSFW_ROLE_ID}" if is_nsfw else "")

    # build embed bodies using updated (YAML) state
    unlocked_lines = deduplicate([format_stored_title(t) for t in new_history["unlocked"]])
    unlocked_md = "\n".join(unlocked_lines)

    locked_lines = deduplicate([format_stored_title(t) for t in new_history["locked"]])
    if locked_lines:
        # mark newest locked arc with pink arrow
        locked_lines[-1] = "<a:9410pinkarrow:1368139217556996117>" + locked_lines[-1]
    locked_md = "\n".join(locked_lines) if locked_lines else "None"

    # 6. build Discord messages (exactly your emoji soup 💖)
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

    embed_unlocked = {
        "description": unlocked_md,
        "color": 0xFFF9BF
    } if unlocked_lines else None

    embed_locked = {
        "description": f"||{locked_md}||",
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

    # 7. send 4 Discord messages (header, unlocked, locked, footer)
    header_ok = False
    try:
        post_discord_message(
            content_header,
            embeds=None,
            suppress_embeds=True
        )
        header_ok = True
        print(f"✅ Header sent for: {announce_full}")
    except requests.RequestException as e:
        print(f"⚠️ Header send failed: {e}", file=sys.stderr)

    # only send unlocked embed if there's anything unlocked
    if unlocked_lines and embed_unlocked:
        try:
            post_discord_message(
                "<a:5693pinkwings:1368138669004820500> `Unlocked 🔓` <a:5046_bounce_pink:1368138460027813888>",
                embeds=[embed_unlocked],
                suppress_embeds=False
            )
            print("✅ Unlocked embed sent.")
        except requests.RequestException as e:
            print(f"⚠️ Unlocked send failed: {e}", file=sys.stderr)
    else:
        print("ℹ️ Skipping Unlocked block (no unlocked arcs).")

    try:
        post_discord_message(
            "<a:5693pinkwings:1368138669004820500> `Locked 🔐` <a:5046_bounce_pink:1368138460027813888>",
            embeds=[embed_locked],
            suppress_embeds=False
        )
        print("✅ Locked embed sent.")
    except requests.RequestException as e:
        print(f"⚠️ Locked send failed: {e}", file=sys.stderr)

    try:
        post_discord_message(
            footer_and_react,
            embeds=None,
            suppress_embeds=True
        )
        print("✅ Footer/react sent.")
    except requests.RequestException as e:
        print(f"⚠️ Footer/react send failed: {e}", file=sys.stderr)

    # 8. mark that we've announced this arc so we won't re-announce
    if header_ok:
        new_history["last_announced"] = announce_full
    else:
        print("⚠️ Not updating last_announced because header send failed.")

    # 9. save + commit
    save_history(new_history, hist_path)
    commit_history_update(hist_path)
    print(f"📌 Finished announcing and recorded last_announced = {new_history['last_announced']}")


def main():
    # go through HOSTING_SITE_DATA, but only run for novels we mapped in ARC_YAML_MAP
    for host_name, host_data in HOSTING_SITE_DATA.items():
        for novel_title, details in host_data.get("novels", {}).items():

            yaml_path = ARC_YAML_MAP.get(novel_title)
            if not yaml_path:
                continue  # only handle Mistmint manual YAML novels

            novel = {
                "novel_title":      novel_title,
                "role_mention":     details.get("discord_role_id", ""),
                "host":             host_name,
                "novel_link":       details.get("novel_url", ""),
                "custom_emoji":     details.get("custom_emoji", ""),
                "discord_role_url": details.get("discord_role_url", ""),
                "history_file":     details.get("history_file", ""),
            }

            if not novel["history_file"]:
                print(f"⚠️ No history_file for {novel_title}, skipping.")
                continue

            if not os.path.exists(yaml_path):
                print(f"⚠️ YAML file {yaml_path} not found for {novel_title}, skipping.")
                continue

            process_mistmint_novel(novel, yaml_path)


if __name__ == "__main__":
    main()
