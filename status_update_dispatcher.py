import json
import os
from pathlib import Path

import requests


FILES_JSON_PATH = Path("config/files.json")


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value

    return str(value or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def _load_local_files_config() -> dict:
    try:
        data = json.loads(FILES_JSON_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"⚠️ Could not read {FILES_JSON_PATH}; optional status update may be skipped: {exc}")
        return {}

    return data if isinstance(data, dict) else {}


def _rss_integrations_url() -> str:
    # Env override still wins for testing.
    env_url = os.environ.get("RSS_FEED_INTEGRATIONS_URL", "").strip()

    if env_url:
        return env_url

    cfg = _load_local_files_config()

    rss_feed = cfg.get("rss_feed", {})
    if isinstance(rss_feed, dict):
        url = str(rss_feed.get("integrations_url") or "").strip()
        if url:
            return url

    # Optional support for flat shape too.
    return str(cfg.get("rss_feed_integrations_url") or "").strip()


def _load_rss_integrations() -> dict:
    url = _rss_integrations_url()

    if not url:
        print("ℹ️ No RSS integrations URL configured; skipping optional status update.")
        return {}

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"⚠️ Could not fetch rss-feed integrations.json; skipping status update: {exc}")
        return {}

    return data if isinstance(data, dict) else {}


def _card_status_update_config() -> dict:
    cfg = _load_rss_integrations()
    section = cfg.get("card_status_update", {})
    return section if isinstance(section, dict) else {}


def trigger_status_update(
    title: str,
    host: str,
    *,
    source: str = "free_chapter",
    short_code: str = "",
) -> bool:
    cfg = _card_status_update_config()

    if not _truthy(cfg.get("enabled")):
        print(f"ℹ️ Card status update disabled in rss-feed integrations.json; skipped {title}.")
        return False

    repo = str(cfg.get("repo") or "").strip()
    event_type = str(cfg.get("event_type") or "").strip()

    if not repo or not event_type:
        print("⚠️ card_status_update is enabled but repo/event_type is missing; skipped.")
        return False

    token = os.environ.get("PAT_GITHUB", "").strip()

    if not token:
        print("⚠️ PAT_GITHUB missing; skipped optional card status update.")
        return False

    url = f"https://api.github.com/repos/{repo}/dispatches"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    client_payload = {
        "title": title,
        "host": host,
        "source": str(source or "free_chapter").strip() or "free_chapter",
    }

    normalized_short_code = str(short_code or "").strip().upper()
    if normalized_short_code:
        client_payload["short_code"] = normalized_short_code

    payload = {
        "event_type": event_type,
        "client_payload": client_payload,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as exc:
        print(f"⚠️ Optional card status update failed for {title}: {exc}")
        return False

    if r.status_code >= 300:
        print(f"⚠️ Optional card status update failed for {title}: {r.status_code} {r.text}")
        return False

    print(
        f"✅ Card status update dispatched for {title} ({host}) "
        f"[{client_payload['source']}]"
    )
    return True