import os
import json
import re
import requests
import feedparser
import sys
from novel_mappings import HOSTING_SITE_DATA, get_nsfw_novels

# ─── CONFIG ────────────────────────────────────────────────────────────────────
STATE_PATH = "state.json"
ONGOING_ROLE = "<@&1329502951764525187>"
NSFW_ROLE_ID = "<@&1343352825811439616>"
BOT_TOKEN_ENV  = "DISCORD_BOT_TOKEN"
CHANNEL_ID_ENV = "DISCORD_CHANNEL_ID"
# ────────────────────────────────────────────────────────────────────────────────

def send_bot_message(bot_token: str, channel_id: str, content: str):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type":  "application/json"
    }
    payload = {"content": content, "allowed_mentions":{"parse":["roles"]}, "flags":4}
    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()

def safe_send_bot(bot_token: str, channel_id: str, content: str):
    try:
        send_bot_message(bot_token, channel_id, content)
        print("✅ Message sent via bot")
    except Exception as e:
        print(f"⚠️ Failed to send via bot: {e}", file=sys.stderr)

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
    # 1) parse the paid feed up‐front
    paid_feed = feedparser.parse(novel["paid_feed"])
    last_chap = novel.get("last_chapter", "")
    for e in paid_feed.entries:
        chap = (e.get("chaptername") or "") + (e.get("nameextend") or "")
        if last_chap and last_chap in chap:
            print(f"→ skipping extras for {novel['novel_id']} — full series complete on feed")
            return

    # 2) now load state and guard against completion in state.json
    state    = load_state()
    novel_id = novel["novel_id"]
    meta     = state.setdefault(novel_id, {})
    if meta.get("paid") or meta.get("free") or meta.get("only_free"):
        print(f"→ skipping extras for {novel_id} — already completed (state.json)")
        return

    # 3) NSFW check
    entries = paid_feed.entries
    is_nsfw = (
        novel["novel_title"] in get_nsfw_novels()
        or nsfw_detected(entries, novel["novel_title"])
    )
    print(f"🕵️ is_nsfw={is_nsfw} for {novel['novel_title']}")
    base_mention = novel["role_mention"] + (f" | {NSFW_ROLE_ID}" if is_nsfw else "")

    # 4) see what’s actually dropped in the feed
    dropped_extras = find_released_extras(paid_feed, "extra")
    dropped_ss     = find_released_extras(paid_feed, "side story")
    max_ex = max(dropped_extras) if dropped_extras else 0
    max_ss = max(dropped_ss)     if dropped_ss     else 0

    # 5) only announce when something new appears
    # 🔒 cap to one announcement ever
    if meta.get("extra_announced"):
        return
    last = state.get(novel_id, {}).get("last_extra_announced", 0)
    current = max(max_ex, max_ss)
    if current > last:
        # — extract totals from config —
        m_ex   = re.search(r"(\d+)\s*extras?", novel["chapter_count"], re.IGNORECASE)
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
        base = f"<:babypinkarrowleft:1365566594503147550>***[{novel['novel_title']}]({novel['novel_link']})***<:babypinkarrowright:1365566635838275595>"
        extra_label = "extra" if tot_ex == 1 else "extras"
        ss_label    = "side story" if tot_ss == 1 else "side stories"
        
        if tot_ex and tot_ss:
            remaining = (
                f"{base} is almost at the very end — just "
                f"{tot_ex} {extra_label} and {tot_ss} {ss_label} left before we wrap up this journey for good  <:turtle_cowboy2:1365266375274266695>"
            )
        elif tot_ex:
            remaining = (
                f"{base} is almost at the very end — just "
                f"{tot_ex} {extra_label} left before we wrap up this journey for good  <:turtle_cowboy2:1365266375274266695>"
            )
        elif tot_ss:
            remaining = (
                f"{base} is almost at the very end — just "
                f"{tot_ss} {ss_label} left before we wrap up this journey for good  <:turtle_cowboy2:1365266375274266695>"
            )
        else:
            remaining = (
                f"{base} is at the very end — no extras or side stories left!  <:turtle_cowboy2:1365266375274266695>"
            )

        # — assemble & send the Discord message —
        msg = (
            f"{base_mention} | {ONGOING_ROLE} <a:Heart1:1365676465059794985>\n"
            f"## :lotus:<a:greensparklingstars:1365569873845157918>NEW {disp_label} JUST DROPPED<a:greensparklingstars:1365569873845157918>:lotus:\n"
            f"{remaining}\n"
            f"{cm} in {novel['host']}'s advance access today. "
            f"Thanks for sticking with this one ‘til the end. It means a lot. "
            f"Please show your final love and support by leaving comments on the site~ <:turtlelovefamily:1365266991690285156> :heart_hands:"
        )
        bot_token   = os.getenv(BOT_TOKEN_ENV)
        channel_id  = os.getenv(CHANNEL_ID_ENV)
        
        if bot_token and channel_id:
            safe_send_bot(bot_token, channel_id, msg)
            print(f"✅ Bot sent extras notification for {novel['novel_title']}")
        else:
            print("⚠️ Bot token or channel ID missing; skipped bot post")

        # update state
        meta["last_extra_announced"] = current
        meta["extra_announced"]      = True   # never fire again
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
