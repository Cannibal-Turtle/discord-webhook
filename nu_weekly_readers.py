#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nu_weekly_readers.py

Fetches Novel Updates "Reading Lists" counts for any novels that declare
`novelupdates_feed_url` in your local `novel_mappings.py`, computes deltas
vs. the last saved run, and (optionally) posts/edits a Discord message with
an embed-only weekly report.

How it works
------------
- For each novel in HOSTING_SITE_DATA with a `novelupdates_feed_url`,
  derive the NU series page URL (strip trailing "/feed/") and request it.
- Parse the HTML for the snippet:  `On <b class="rlist">N</b> Reading Lists`.
- Compare to the previously saved count in a JSON state file
  (default: `nu_readers_state.json` at repo root).
- Build a single-embed report with your requested formatting and either
  print it (dry-run) or send to Discord using a bot token.

Environment variables (optional)
--------------------------------
- NU_STATE_PATH:        Path to the JSON state file (default: state_rss.json)
- DISCORD_BOT_TOKEN:    If set, the script will send/edit a message via Bot HTTP API
- (Optional) You can override the target thread with `--channel <id>` at runtime; otherwise it posts to 1435350071909548162.
- DISCORD_MESSAGE_ID:   If set, PATCH (edit) this message instead of creating a new one
- ALLOW_ROLE_PINGS:     If "true" (default), allow role mentions in embed to ping

Notes
-----
- The embed includes an ISO8601 `timestamp` set to UTC; Discord will localize it for viewers.

GitHub Actions notes
--------------------
- Add a step to `pip install requests` (no other deps needed).
- If you want state persisted, commit `nu_readers_state.json` after running.
- Schedule weekly and run this script; the delta will be week-over-week.

"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import datetime as dt
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse

import requests

# Import your mapping from the repo
try:
    from novel_mappings import HOSTING_SITE_DATA
except Exception as e:
    print("[fatal] Could not import novel_mappings.HOSTING_SITE_DATA:", e, file=sys.stderr)
    raise

# ---------------------------- constants --------------------------------
AUTHOR_NAME = "Novel Updates"
AUTHOR_ICON = "https://www.novelupdates.com/appicon.png"
EMBED_COLOR_HEX = os.environ.get("EMBED_COLOR", "2d3f51")

# Default thread/channel to post into if no env/CLI provided (user-specified)
CHANNEL_DEFAULT = "1435350071909548162"

TITLE_BOX = (
    "╔═══*.·:·.☽✧    ✦    ✧☾.·:·.*═══╗\n"
    "              **weekly NU report**\n"
    "╚═══*.·:·.☽✧    ✦    ✧☾.·:·.*═══╝"
)

DEFAULT_STATE_PATH = os.environ.get("NU_STATE_PATH", "state_rss.json")
# Timestamp in embeds will use UTC so Discord localizes it per user; TZ env not needed.
DEFAULT_TZ = "UTC"

# tolerant of tiny NU changes; allows singular/plural
_RLIST_RE = re.compile(
    r"On\s*<b[^>]*class=[\"']?rlist[\"']?[^>]*>\s*([\d,]+)\s*</b>\s*Reading\s+Lists?",
    re.IGNORECASE | re.DOTALL,
)

# Accept "12345" or "<@&12345>" and normalize to "<@&12345>"
_ROLE_RE = re.compile(r"^\s*(?:<@&)?(\d+)>?\s*$")

# ---------------------------- helpers ----------------------------------

def _now_tz(tz_name: str) -> dt.datetime:
    # Kept for compatibility, but we always post UTC timestamps in the embed.
    return dt.datetime.now(dt.timezone.utc)


def _series_url_from_feed(feed_url: str) -> Optional[str]:
    if not feed_url:
        return None
    u = feed_url.strip()
    if not u:
        return None
    # NU series feeds are .../series/<slug>/feed/ ; strip the trailing 'feed' bit
    if "/feed" in u:
        base = u.split("/feed")[0].rstrip("/")
        return base + "/"
    # If someone passed series URL already, just return it normalized
    return u if u.endswith("/") else (u + "/")


def _slug_from_series_url(series_url: str) -> str:
    p = urlparse(series_url)
    parts = [s for s in p.path.split("/") if s]
    slug = parts[-1] if parts else series_url
    return slug


def _novel_key(novel_title: str, nd: Dict[str, any], series_url: str) -> str:
    # 1) explicit override wins
    sk = (nd.get("state_key") or "").strip()
    if sk:
        return sk.upper()
    # 2) default to mapping title (normalized)
    return re.sub(r"\W+", "_", str(novel_title)).strip("_").upper()


def _normalize_role_mention(raw: str) -> str:
    if not raw:
        return ""
    m = _ROLE_RE.match(raw)
    return f"<@&{m.group(1)}>" if m else raw.strip()


def _fetch_reading_lists_count(series_url: str, timeout: int = 30) -> Optional[int]:
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.7",
        "Connection": "close",
        "Referer": series_url,
    }

    def _try_parse(text: str) -> Optional[int]:
        m = _RLIST_RE.search(text)
        if not m:
            return None
        try:
            return int(m.group(1).replace(",", ""))
        except Exception:
            return None

    # 1) requests first
    try:
        r = requests.get(series_url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            n = _try_parse(r.text)
            if n is not None:
                return n
            print(f"[warn] Pattern not found on {series_url}. Snippet: {r.text[:250]!r}")
        else:
            print(f"[warn] GET {series_url} -> HTTP {r.status_code}")
    except Exception as e:
        print(f"[warn] requests exception {series_url}: {e}")

    # 2) optional fallback if CF blocks the runner
    try:
        import cloudscraper  # pip install cloudscraper
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        r2 = scraper.get(series_url, timeout=timeout)
        if r2.status_code == 200:
            n = _try_parse(r2.text)
            if n is not None:
                return n
            print(f"[warn] cloudscraper miss {series_url}. Snippet: {r2.text[:250]!r}")
        else:
            print(f"[warn] cloudscraper GET {series_url} -> HTTP {r2.status_code}")
    except ImportError:
        print("[info] cloudscraper not installed; skipping CF fallback")
    except Exception as e:
        print(f"[warn] cloudscraper exception {series_url}: {e}")

    return None

# --------------------------- state handling -----------------------------

def _acquire_lock(lock_path: str, timeout: int = 30) -> Optional[int]:
    """Simple cross-run lock using an exclusive lock file (best-effort)."""
    start = time.time()
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, str(os.getpid()).encode("utf-8", "ignore"))
            return fd
        except FileExistsError:
            if time.time() - start > timeout:
                print(f"[warn] lock timeout on {lock_path}; proceeding unlocked")
                return None
            time.sleep(0.5)


def _release_lock(fd: Optional[int], lock_path: str) -> None:
    try:
        if fd is not None:
            os.close(fd)
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        pass

# --------------------------- state handling -----------------------------

def _load_state(path: str) -> Dict[str, any]:
   if not os.path.exists(path):
       return {}
   try:
       with open(path, "r", encoding="utf-8") as f:
           return json.load(f)
   except Exception as e:
       # keep the broken file for inspection
       try:
           os.replace(path, path + ".bad")
           print(f"[warn] {path} was invalid JSON; moved to {path}.bad ({e})")
       except Exception:
           print(f"[warn] {path} invalid JSON; could not backup ({e})")
       return {}


def _save_state(path: str, data: Dict[str, any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# --------------------------- embed building -----------------------------

def _format_delta(delta: Optional[int]) -> str:
    if delta is None:
        return "*first run*"
    sign = "+" if delta >= 0 else ""
    # Use different wording for negatives to match the user's example
    if delta < 0:
        return f"*{sign}{delta} readers*"  # e.g. *-20 readers*
    else:
        return f"*{sign}{delta} new readers*"  # e.g. *+10 new readers* or *+0 new readers*


def _build_description(lines: List[Tuple[str, int, Optional[int]]]) -> str:
    # lines: list of (role_mention, current_count, delta)
    parts: List[str] = []
    for role, count, delta in lines:
        role_txt = role or "(no-role)"
        parts.append(f"{role_txt} ༺♡༻ {_format_delta(delta)}\n> <:23286kawaiiaccents:1435916448890617948> ̟ !! ***{count} total readers***")
    return "\n".join(parts)


def _build_embed(description: str) -> Dict[str, any]:
    now_utc = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    footer_text = "Data retrieved"
    embed = {
        "author": {"name": AUTHOR_NAME, "icon_url": AUTHOR_ICON},
        "title": TITLE_BOX,
        "description": description,
        "footer": {"text": footer_text},
        "timestamp": now_utc.isoformat().replace("+00:00", "Z"),  # Discord localizes
        "color": int(EMBED_COLOR_HEX, 16),
    }
    return embed


# -------------------------- Discord posting ----------------------------

def _send_or_edit_discord_embed(
    embed: Dict[str, any],
    token: str,
    channel_id: str,
    message_id: Optional[str] = None,
    allow_pings: bool = False,
) -> None:
    url_base = "https://discord.com/api/v10"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "content": "",  # embed-only per user request
        "embeds": [embed],
        "allowed_mentions": {"parse": ["roles"] if allow_pings else []},
    }

    sess = requests.Session()
    try:
        if message_id:
            url = f"{url_base}/channels/{channel_id}/messages/{message_id}"
            r = sess.patch(url, headers=headers, json=payload, timeout=30)
        else:
            url = f"{url_base}/channels/{channel_id}/messages"
            r = sess.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code // 100 != 2:
            print("[error] Discord API failure:", r.status_code, r.text, file=sys.stderr)
        else:
            obj = r.json()
            mid = obj.get("id")
            print(f"[ok] Discord message {'edited' if message_id else 'sent'}: id={mid}")
    finally:
        sess.close()


# ------------------------------- main ----------------------------------

def collect_targets() -> List[Tuple[str, str, str, str]]:
    """
    Return list of (key, novel_title, role_mention, series_url)
    for all novels that have `novelupdates_feed_url`.
    """
    out: List[Tuple[str, str, str, str]] = []
    for host, cfg in (HOSTING_SITE_DATA or {}).items():
        novels = (cfg.get("novels") or {})
        for novel_title, nd in novels.items():
            nu_feed = (nd.get("novelupdates_feed_url") or "").strip()
            if not nu_feed:
                continue
            series_url = _series_url_from_feed(nu_feed)
            if not series_url:
                continue
            key = _novel_key(novel_title, nd, series_url)
            role = _normalize_role_mention(nd.get("discord_role_id", ""))
            out.append((key, novel_title, role, series_url))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-only", action="store_true", help="Don't post to Discord; print report only")
    ap.add_argument("--state", help="State JSON path (default env NU_STATE_PATH or nu_readers_state.json)")
    ap.add_argument("--channel", help="Discord channel id (overrides default thread id)")
    ap.add_argument("--message", help="Discord message id to edit (overrides env)")
    args = ap.parse_args(argv)

    state_path = args.state or DEFAULT_STATE_PATH
    lock_fd = _acquire_lock(state_path + ".lock")

    targets = collect_targets()
    print(f"[info] Found {len(targets)} NU targets")
    for _, title, role, url in targets:
        print(f"[info]  • {title}  {role or '(no-role)'}  -> {url}")
    if not targets:
        print("[info] No novels with novelupdates_feed_url found in mappings.")
        _release_lock(lock_fd, state_path + ".lock")
        return 0

    state = _load_state(state_path)
    nu = state.get("nu_readers", {}) if isinstance(state, dict) else {}
    prev_counts: Dict[str, Dict[str, any]] = nu.get("counts", {})

    results: List[Tuple[str, int, Optional[int]]] = []  # (role_mention, current, delta)
    new_counts: Dict[str, Dict[str, any]] = dict(prev_counts)  # copy

    for key, title, role, url in targets:
        curr = _fetch_reading_lists_count(url)
        if curr is None:
            prev_entry = prev_counts.get(key)
            prev_val = (prev_entry or {}).get("count")
            if prev_val is None:
                print(f"[skip] No data for {title} ({url})")
                continue
            results.append((role, prev_val, None))  # first-run/unknown delta
            continue

        prev_entry = prev_counts.get(key)
        delta: Optional[int]
        if prev_entry is None:
            delta = None
        else:
            delta = curr - int(prev_entry.get("count", 0))

        results.append((role, curr, delta))
        new_counts[key] = {"count": int(curr), "when": dt.datetime.utcnow().isoformat() + "Z"}

    description = _build_description(results)
    if not description.strip():
        description = "_No data this week (no NU counts retrieved)._"
    embed = _build_embed(description)

    # Persist state (with lock)
    nu["last_updated"] = dt.datetime.utcnow().isoformat() + "Z"
    nu["counts"] = new_counts
    state["nu_readers"] = nu
    _save_state(state_path, state)
    _release_lock(lock_fd, state_path + ".lock")
    print(f"[ok] State saved: {state_path}")

    # Decide to post
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()

    # Post specifically to your given thread unless overridden via --channel
    channel_id = args.channel or CHANNEL_DEFAULT
    message_id = (
        args.message
        or os.environ.get("DISCORD_MESSAGE_ID", "").strip()
        or os.environ.get("DISCORD_NU_MESSAGE_ID", "").strip()
    )
    # Default to pinging roles unless explicitly disabled
    allow_pings = os.environ.get("ALLOW_ROLE_PINGS", "true").lower() == "true"

    if args.print_only or not token or not channel_id:
        print("\n=== EMBED PREVIEW (dry-run) ===")
        print(json.dumps({"content": "", "embeds": [embed]}, ensure_ascii=False, indent=2))
        return 0

    _send_or_edit_discord_embed(embed, token, channel_id, message_id or None, allow_pings=allow_pings)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
