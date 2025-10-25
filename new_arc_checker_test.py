#!/usr/bin/env python3
"""
new_arc_checker_dryrun.py

Run the REAL new-arc detection & numbering logic, but:
- DRY_RUN=true (default): never write history, never commit, never hit Discord
- DRY_RUN=false: send the Discord messages, but STILL don't write/commit

It prints:
- what it detected in the feeds
- what it would add/remove in history (diff)
- the final "would-save" JSON snapshot
"""

import os
import re
import json
import sys
import requests
import feedparser
from copy import deepcopy
from novel_mappings import HOSTING_SITE_DATA, get_nsfw_novels

# ─── ENV & FLAGS ──────────────────────────────────────────────────────
BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN", "")
CHANNEL_ID  = os.getenv("DISCORD_CHANNEL_ID", "")
DRY_RUN     = os.getenv("DRY_RUN", "true").lower() == "true"

ONGOING_ROLE = "<@&1329502951764525187>"
NSFW_ROLE_ID = "<@&1343352825811439616>"

# ─── EMOJI DIGITS ─────────────────────────────────────────────────────
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
    return ''.join(DIGIT_EMOJI[d] for d in str(n))

# ─── SMALL HELPERS (match your prod logic) ────────────────────────────
def deduplicate(lst):
    seen = set(); out = []
    for x in lst:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def extract_arc_number(title):
    m = re.search(r"【Arc\s*(\d+)】", title)
    return int(m.group(1)) if m else None

def format_stored_title(title):
    m = re.match(r"(【Arc\s+\d+】)\s*(.*)", title)
    return f"**{m.group(1)}**{m.group(2)}" if m else f"**{title}**"

def clean_feed_title(raw_title):
    return (raw_title or "").replace("*", "").strip()

def extract_arc_title(nameextend):
    clean = (nameextend or "").strip("* ").strip()
    clean = re.sub(r"(?:\s+001|\(1\)|\.\s*1)$", "", clean).strip()
    return clean

def strip_any_number_prefix(s: str) -> str:
    return re.sub(r"^.*?\d+[^\w\s]*\s*", "", s or "")

def nsfw_detected(feed_entries, novel_title):
    title_l = (novel_title or "").lower()
    for e in feed_entries:
        et = (e.get("title") or "").lower()
        cat = (e.get("category") or "").lower()
        if title_l in et and "nsfw" in cat:
            return True
    return False

def next_arc_number(history):
    last = history.get("last_announced", "")
    n = extract_arc_number(last)
    if n: return n + 1
    nums = []
    for sec in ("unlocked","locked"):
        for t in history.get(sec, []):
            m = extract_arc_number(t)
            if m: nums.append(m)
    return (max(nums) if nums else 0) + 1

def load_history(history_file):
    if not history_file:
        return {"unlocked": [], "locked": [], "last_announced": ""}
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("unlocked", [])
        data.setdefault("locked", [])
        data.setdefault("last_announced", "")
        return data
    except FileNotFoundError:
        return {"unlocked": [], "locked": [], "last_announced": ""}

def print_history_diff(before, after, label):
    def strip_arc_prefixes(lst):
        return [re.sub(r"^【Arc\s*\d+】\s*", "", s) for s in lst]
    print(f"\n— {label} DIFF —")
    b_u, b_l = before.get("unlocked", []), before.get("locked", [])
    a_u, a_l = after.get("unlocked", []),  after.get("locked",  [])
    added_u   = [x for x in a_u if x not in b_u]
    removed_u = [x for x in b_u if x not in a_u]
    added_l   = [x for x in a_l if x not in b_l]
    removed_l = [x for x in b_l if x not in a_l]
    if added_u:   print("  + unlocked:", added_u)
    if removed_u: print("  - unlocked:", removed_u)
    if added_l:   print("  + locked:", added_l)
    if removed_l: print("  - locked:", removed_l)
    if before.get("last_announced","") != after.get("last_announced",""):
        print("  ~ last_announced:", after.get("last_announced"))
    if not any([added_u, removed_u, added_l, removed_l]) and \
       before.get("last_announced","") == after.get("last_announced",""):
        print("  (no changes)")

def send_discord_message(content=None, embed=None):
    """Respects DRY_RUN: print instead of sending."""
    if DRY_RUN:
        print("🧪 DRY_RUN would send:")
        if content: print("CONTENT >>>\n" + content + "\n<<< END CONTENT")
        if embed:   print("EMBED >>>\n" + json.dumps(embed, indent=2, ensure_ascii=False) + "\n<<< END EMBED")
        print("────────────────────────────")
        return True
    if not (BOT_TOKEN and CHANNEL_ID):
        print("❌ Missing DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID", file=sys.stderr)
        return False
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
    headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
    payload = {"allowed_mentions": {"parse": ["roles"]}}
    if content is not None:
        payload["content"] = content
        if embed is None: payload["flags"] = 4
    if embed is not None:
        payload["embeds"] = [embed]
    r = requests.post(url, headers=headers, json=payload)
    if not r.ok:
        print(f"⚠️ Discord error {r.status_code}: {r.text}", file=sys.stderr)
        return False
    return True

# ─── CORE (same behavior as prod, but no writes) ─────────────────────
def process_arc(novel):
    print(f"\n=== {novel['novel_title']} ===")
    free_feed = feedparser.parse(novel["free_feed"])
    paid_feed = feedparser.parse(novel["paid_feed"])
    print(f"🌐 feeds: free={len(free_feed.entries)} paid={len(paid_feed.entries)}")

    is_nsfw = (novel["novel_title"] in get_nsfw_novels()
               or nsfw_detected(free_feed.entries + paid_feed.entries, novel["novel_title"]))
    base_mention = novel["role_mention"] + (f" | {NSFW_ROLE_ID}" if is_nsfw else "")

    hist_path = novel.get("history_file") or ""
    before = load_history(hist_path)
    print(f"📂 loaded {hist_path or '(no file)'}: "
          f"{len(before['unlocked'])} unlocked / {len(before['locked'])} locked "
          f"(last_announced={before['last_announced']})")
    history = deepcopy(before)

    def is_new_marker(raw):
        return bool(re.search(r"\b001\b|\(1\)|\.\s*1$", raw or ""))

    def extract_new_bases(feed):
        bases = []
        for e in feed.entries:
            raw_vol    = (e.get("volume") or "").replace("\u00A0", " ").strip()
            raw_extend = (e.get("nameextend") or "").replace("\u00A0", " ").strip()
            raw_chap   = (e.get("chaptername") or "").replace("\u00A0", " ").strip()
            if not (is_new_marker(raw_extend) or is_new_marker(raw_chap)):
                continue
            if raw_vol:
                base = clean_feed_title(raw_vol)
            elif raw_extend:
                base = extract_arc_title(raw_extend)
            else:
                base = raw_chap
            bases.append(strip_any_number_prefix(base))
        return bases

    free_new = extract_new_bases(free_feed)
    paid_new = extract_new_bases(paid_feed)
    print(f"🔍 new-markers: free={len(free_new)} paid={len(paid_new)}")

    free_created_new_arc = False
    paid_created_new_arc = False

    # Free side (unlock or brand-new-free)
    for base in free_new:
        matched_locked = False
        for full in history["locked"][:]:
            if full.endswith(base):
                matched_locked = True
                history["locked"].remove(full)
                if full not in history["unlocked"]:
                    history["unlocked"].append(full)
                    print(f"🔓 unlocked: {full}")
                break
        if not matched_locked:
            seen_bases = [re.sub(r"^【Arc\s*\d+】", "", t) for t in (history["unlocked"] + history["locked"])]
            if base not in seen_bases:
                n = next_arc_number(history)
                full = f"【Arc {n}】{base}"
                history["unlocked"].append(full)
                free_created_new_arc = True
                print(f"🌿 brand-new free arc: {full}")

    # Paid side (always lock)
    seen_after_free = [re.sub(r"^【Arc\s*\d+】", "", t) for t in (history["unlocked"] + history["locked"])]
    for base in paid_new:
        if base not in seen_after_free:
            n = next_arc_number(history)
            full = f"【Arc {n}】{base}"
            history["locked"].append(full)
            paid_created_new_arc = True
            print(f"🔐 new locked arc: {full}")

    # Dedupe lists
    history["unlocked"] = deduplicate(history["unlocked"])
    history["locked"]   = deduplicate(history["locked"])

    # Special bootstrap: first arc is free, nothing locked yet → persist numbering
    scenario_first_arc_free_only = (free_created_new_arc and not paid_created_new_arc and not history["locked"])
    if scenario_first_arc_free_only:
        print("\n🌱 First arc started FREE. Would SAVE numbering (no Discord ping).")
        print_history_diff(before, history, "BOOTSTRAP")
        print("\n📄 WOULD-SAVE JSON ↓↓↓")
        print(json.dumps(history, indent=2, ensure_ascii=False))
        return

    # Nothing locked at all → nothing to announce
    new_full = history["locked"][-1] if history["locked"] else None
    if not new_full:
        print("\nℹ️ No locked arcs exist → nothing to announce.")
        print_history_diff(before, history, "NO-LOCKED")
        print("\n📄 WOULD-SAVE JSON (not saving in dry-run):")
        print(json.dumps(history, indent=2, ensure_ascii=False))
        return

    # Already announced latest?
    if new_full == history.get("last_announced", ""):
        print(f"\n✅ Latest locked already announced: {new_full}")
        print_history_diff(before, history, "ALREADY-ANNOUNCED")
        print("\n📄 WOULD-SAVE JSON (not saving in dry-run):")
        print(json.dumps(history, indent=2, ensure_ascii=False))
        return

    # Build messages (exactly like prod)
    world_num   = extract_arc_number(new_full)
    world_emoji = number_to_emoji(world_num) if world_num is not None else ""

    unlocked_md = "\n".join(format_stored_title(t) for t in history["unlocked"])
    locked_lines = [format_stored_title(t) for t in history["locked"]]
    locked_lines = deduplicate(locked_lines)
    if locked_lines:
        locked_lines[-1] = "<a:9410pinkarrow:1368139217556996117>" + locked_lines[-1]
    locked_md = "\n".join(locked_lines)

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
    embed_unlocked = {"description": f"||{unlocked_md}||" if unlocked_md else "None", "color": 0xFFF9BF}
    embed_locked   = {"description": f"||{locked_md}||" if locked_md else "None", "color": 0xA87676}
    footer_and_react = (
        "╰───────────────────────┄ °❀\n"
        f"> *Advance access is ready for you on {novel['host']}! <a:holo_diamond:1365566087277711430>*\n"
        + "<:pinkdiamond_border:1365575603734183936>" * 6
        + "\n-# React to the "
        + f"{novel['custom_emoji']} @ {novel['discord_role_url']} "
        + "to get notified on updates and announcements "
        "<a:LoveLetter:1365575475841339435>"
    )

    # "Send" (or print)
    ok1 = send_discord_message(content=content_header, embed=None)
    ok2 = send_discord_message(
        content="<a:5693pinkwings:1368138669004820500> `Unlocked 🔓` <a:5046_bounce_pink:1368138460027813888>",
        embed=embed_unlocked
    )
    ok3 = send_discord_message(
        content="<a:5693pinkwings:1368138669004820500> `Locked 🔐` <a:5046_bounce_pink:1368138460027813888>",
        embed=embed_locked
    )
    ok4 = send_discord_message(content=footer_and_react, embed=None)

    # Would update last_announced *after* successful header in prod:
    after = deepcopy(history)
    if ok1:
        after["last_announced"] = new_full

    print_history_diff(before, after, "AFTER-SEND")

    print("\n📄 WOULD-SAVE JSON ↓↓↓ (dry-run never writes):")
    print(json.dumps(after, indent=2, ensure_ascii=False))


def main():
    if DRY_RUN:
        print("🧪 DRY_RUN=true — no writes, no commits, no Discord. Preview only.\n")
    else:
        print("⚠️ DRY_RUN=false — will POST to Discord, but still won't write/commit history.\n")

    for host, host_data in HOSTING_SITE_DATA.items():
        for title, d in host_data.get("novels", {}).items():
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

if __name__ == "__main__":
    main()
