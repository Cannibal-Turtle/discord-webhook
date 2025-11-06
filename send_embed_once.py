#!/usr/bin/env python3
import os, json, mimetypes
from urllib.parse import urlparse
import requests

TOKEN      = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = os.environ["DISCORD_CHANNEL_ID"]
TITLE      = os.environ.get("EMBED_TITLE","")
DESC       = os.environ.get("EMBED_DESC","")
IMAGE_URL  = os.environ.get("IMAGE_URL","").strip()
PING_LINE  = os.environ.get("PING_LINE","").strip()
BLUR       = os.environ.get("BLUR_SPOILER","0").strip() == "1"
USE_BIG    = os.environ.get("USE_BIG_IMAGE","0").strip() == "1"

API = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
HEAD_BOT = {"Authorization": f"Bot {TOKEN}"}

def _guess_name_and_mime(url, default="image.jpg"):
    path = urlparse(url).path
    name = (os.path.basename(path) or default)
    if "." not in name:  # S3 keys sometimes lack ext
        name += ".jpg"
    mime = mimetypes.guess_type(name)[0] or "image/jpeg"
    return name, mime

def send_with_attachment(img_bytes, attach_name, embed):
    payload = {
        "content": PING_LINE,
        "embeds": [embed],
        "allowed_mentions": {"parse": ["roles"]}
    }
    files = {"files[0]": (attach_name, img_bytes, mimetypes.guess_type(attach_name)[0] or "image/jpeg")}
    r = requests.post(API, headers=HEAD_BOT,
                      data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                      files=files)
    r.raise_for_status()

def send_json(embed):
    payload = {
        "content": PING_LINE,
        "embeds": [embed],
        "allowed_mentions": {"parse": ["roles"]}
    }
    r = requests.post(API, headers={**HEAD_BOT, "Content-Type":"application/json"}, json=payload)
    r.raise_for_status()

embed = {
    "title": TITLE,
    "description": DESC,
    "color": 0x5865F2,  # any
}

if IMAGE_URL:
    if BLUR:
        # Download, re-upload as SPOILER_ attachment
        try:
            rb = requests.get(IMAGE_URL, timeout=20)
            rb.raise_for_status()
            base_name, _ = _guess_name_and_mime(IMAGE_URL)
            attach_name = f"SPOILER_{base_name}"
            slot = "image" if USE_BIG else "thumbnail"
            embed[slot] = {"url": f"attachment://{attach_name}"}
            send_with_attachment(rb.content, attach_name, embed)
        except Exception as e:
            # fallback to plain URL if download fails
            slot = "image" if USE_BIG else "thumbnail"
            embed[slot] = {"url": IMAGE_URL}
            send_json(embed)
    else:
        # No blur → just use remote URL
        slot = "image" if USE_BIG else "thumbnail"
        embed[slot] = {"url": IMAGE_URL}
        send_json(embed)
else:
    send_json(embed)
