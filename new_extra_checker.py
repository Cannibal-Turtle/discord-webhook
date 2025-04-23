import os
import json
import re
import requests
import feedparser
from novel_mappings import HOSTING_SITE_DATA, get_nsfw_novels

STATE_PATH = "state.json"
ONGOING_ROLE = "<@&1329502951764525187>"
NSFW_ROLE_ID = "<@&1343352825811439616>"

def load_state(path=STATE_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_state(state, path=STATE_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def nsfw_detected(feed_entries, novel_title):
    """Checks if NSFW category exists for this novel."""
    for entry in feed_entries:
        if novel_title.lower() in entry.get("title", "").lower() and "nsfw" in entry.get("category","").lower():
            print(f"⚠️ NSFW detected in entry: {entry.get('title')}")
            return True
    return False

def find_released_extras(paid_feed, raw_kw):
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

def process_extras(novel):
    paid_feed = feedparser.parse(novel["paid_feed"])

    # 0) NSFW check
    is_nsfw = (
        novel["novel_title"] in get_nsfw_novels()
        or nsfw_detected(free_feed.entries + paid_feed.entries, novel["novel_title"])
    )
    print(f"🕵️ is_nsfw={is_nsfw} for {novel['novel_title']}")
    base_mention = novel["role_mention"] + (f" | {NSFW_ROLE_ID}" if is_nsfw else "")

    # 1) see what’s actually dropped in the feed
    dropped_extras = find_released_extras(paid_feed, "extra")
    dropped_ss     = find_released_extras(paid_feed, "side story")
    max_ex = max(dropped_extras) if dropped_extras else 0
    max_ss = max(dropped_ss)     if dropped_ss     else 0

    # 2) only announce when something new appears
    state = load_state()
    novel_id = novel.get("novel_id", novel.get("novel_title"))
    last = state.get(novel_id, {}).get("last_extra_announced", 0)
    current = max(max_ex, max_ss)
    if current > last:
        # — extract totals from config —
        m_ex   = re.search(r"(\d+)\s*extras?",       novel["chapter_count"], re.IGNORECASE)
        m_ss   = re.search(r"(\d+)\s*(?:side story|side stories)", novel["chapter_count"], re.IGNORECASE)
        tot_ex = int(m_ex.group(1)) if m_ex else 0
        tot_ss = int(m_ss.group(1)) if m_ss else 0

        # — build the header label —
        parts = []
        if tot_ex: parts.append("EXTRA" if tot_ex == 1 else "EXTRAS")
        if tot_ss: parts.append("SIDE STORY" if tot_ss == 1 else "SIDE STORIES")
        disp_label = " + ".join(parts)

        # — decide which “dropped” message to use —
        new_ex = max_ex > last
        new_ss = max_ss > last

        if new_ex and not new_ss:
            if max_ex == 1:
                cm = "The first of those extras just dropped"
            elif max_ex < tot_ex:
                cm = "New extras just dropped"
            else:
                cm = "All extras just dropped"
        elif new_ss and not new_ex:
            if max_ss == 1:
                cm = "The first of those side stories just dropped"
            elif max_ss < tot_ss:
                cm = "New side stories just dropped"
            else:
                cm = "All side stories just dropped"
        else:  # both new_ex and new_ss
            if max_ex == tot_ex and max_ss == tot_ss:
                cm = "All extras and side stories just dropped"
            else:
                cm = "New extras and side stories just dropped"

        # — build the “remaining” line —
        base = f"***[《{base_mention}》]({novel['novel_link']})***"
        extra_label = "extra" if tot_ex == 1 else "extras"
        ss_label    = "side story" if tot_ss == 1 else "side stories"
        remaining = (
            f"{base} is almost at the very end — just "
            f"{tot_ex} {extra_label} and {tot_ss} {ss_label} left before we wrap up this journey for good."
        )

        # — assemble & send the Discord message —
        msg = (
            f"{base_mention} | {ONGOING_ROLE}\n"
            f"## :lotus:･ﾟ✧ NEW {disp_label} JUST DROPPED ✧ﾟ･:lotus:\n"
            f"{remaining}\n"
            f"{cm} in {novel['host']}'s advance access today. "
            f"Thanks for sticking with this one ‘til the end. It means a lot. "
            f"Please show your final love and support by leaving comments on the site~ :heart_hands:"
        )
        requests.post(
            os.getenv("DISCORD_WEBHOOK"),
            json={"content": msg, "flags": 4, "allowed_mentions": {"parse": ["roles"]}}
        )

        # update state
        state.setdefault(novel_id, {})["last_extra_announced"] = current
        save_state(state)

if __name__ == "__main__":
    novels = []
    for host, host_data in HOSTING_SITE_DATA.items():
        for title, d in host_data.get("novels", {}).items():
            if not d.get("paid_feed"):
                continue
            novels.append({
                "novel_id":      title,
                "novel_title":   title,
                "paid_feed":     d["paid_feed"],
                "chapter_count": d.get("chapter_count",""),
                "host":          host,
                "novel_link":    d.get("novel_url",""),
                "role_mention":  d.get("discord_role_id","")
            })
    for novel in novels:
        process_extras(novel)
