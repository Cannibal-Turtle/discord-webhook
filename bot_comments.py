import os
import json
import asyncio
import feedparser
from dateutil import parser as dateparser
import aiohttp

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN       = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID  = os.environ["DISCORD_COMMENTS_CHANNEL"]
STATE_FILE  = "state_comments.json"
RSS_URL     = "https://cannibal-turtle.github.io/rss-feed/aggregated_comments_feed.xml"
API_URL     = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
# ────────────────────────────────────────────────────────────────────────────────

def load_state():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except:
        init = {"last_guid": None}
        json.dump(init, open(STATE_FILE,"w",encoding="utf-8"), indent=2)
        return init

def save_state(s):
    json.dump(s, open(STATE_FILE,"w",encoding="utf-8"), indent=2)

async def main():
    state   = load_state()
    feed    = feedparser.parse(RSS_URL)
    entries = list(reversed(feed.entries))  # oldest→newest
    guids   = [(e.get("guid") or e.get("id")) for e in entries]
    last    = state["last_guid"]
    to_send = entries[guids.index(last)+1:] if last in guids else entries
    if not to_send:
        print("No new comments.")
        return

    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type":  "application/json"
    }

    async with aiohttp.ClientSession() as sess:
        new_last = last
        for entry in to_send:
            guid        = entry.get("guid") or entry.get("id")
            title       = entry.get("title","").strip()
            role_id     = entry.get("discord_role_id","").strip()
            author      = entry.get("author") or entry.get("dc_creator","")
            chapter     = entry.get("chapter","").strip()
            comment_txt = entry.get("description","").strip()
            reply_chain = entry.get("reply_chain","").strip()
            host        = entry.get("host","").strip()
            host_logo   = (entry.get("hostLogo") or entry.get("hostlogo") or {}).get("url","")
            pubdate_raw = getattr(entry,"published",None)
            ts          = dateparser.parse(pubdate_raw).isoformat() if pubdate_raw else None

            # short title, full comment in description:
            t = f"Comment by {author} 🕊️ {chapter}"
            if len(t)>256: t = t[:253]+"..."

            embed = {
                "title":       t,
                "url":         entry.get("link",""),
                "description": comment_txt + ("\n\n"+reply_chain if reply_chain else ""),
                "timestamp":   ts,
                "color":       int("F0C7A4",16),
                "footer":      {"text": host, "icon_url": host_logo}
            }

            payload = {
                "content": f"New comment for **{title}** || {role_id}",
                "embeds":  [embed]
            }

            async with sess.post(API_URL, headers=headers, json=payload) as r:
                if r.status in (200,204):
                    print("Sent", guid)
                    new_last = guid
                else:
                    print("Error", r.status, await r.text())

        if new_last != last:
            state["last_guid"] = new_last
            save_state(state)

if __name__=="__main__":
    asyncio.run(main())
