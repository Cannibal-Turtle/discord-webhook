# -*- coding: utf-8 -*-
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from dateutil import parser as dateparser


def norm(value: Any) -> str:
    """Return a clean string for template placeholders."""
    if value is None:
        return ""
    return str(value).strip()


def entry_get(entry: Any, *keys: str, default: Any = "") -> Any:
    """
    Case-tolerant getter for feedparser entries.

    feedparser usually behaves like a dict, but names can vary:
      featuredImage / featuredimage
      hostLogo / hostlogo
      dc_creator / creator / author
    """
    for key in keys:
        candidates = [
            key,
            key.lower(),
            key.upper(),
        ]

        # Small camelCase -> lowercase helper for names like shortCode.
        lower_no_underscore = key.replace("_", "").lower()
        candidates.append(lower_no_underscore)

        for candidate in candidates:
            try:
                value = entry.get(candidate)
            except AttributeError:
                value = getattr(entry, candidate, None)

            if value not in (None, ""):
                return value

    return default


def obj_get(obj: Any, key: str, default: Any = "") -> Any:
    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(key, default)

    try:
        return obj.get(key, default)
    except AttributeError:
        return getattr(obj, key, default)


def get_obj_url(entry: Any, *names: str) -> str:
    """Get URL from RSS singleton tags like <featuredImage url="..."/>."""
    for name in names:
        obj = entry_get(entry, name, default=None)
        if obj:
            url = obj_get(obj, "url", "")
            if url:
                return norm(url)
    return ""


def parse_pub_datetime(entry: Any) -> datetime | None:
    """Return timezone-aware pubDate/published datetime, or None."""
    raw = (
        getattr(entry, "published", None)
        or entry_get(entry, "published", "pubDate", "pub_date", default="")
    )

    if not raw:
        return None

    try:
        dt = dateparser.parse(str(raw))
    except Exception:
        return None

    if dt and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def normalize_guid(entry: Any, *, lower_host: bool = False) -> str:
    """
    Composite identity: host::guid.

    Keep lower_host=False for chapter scripts if you want to match your existing
    state keys. Use lower_host=True only in scripts that already lowercased host.
    """
    host = norm(entry_get(entry, "host", default=""))
    if lower_host:
        host = host.lower()

    raw = norm(entry_get(entry, "guid", "id", default=""))
    raw = html.unescape(raw)

    # If GUID is URL-like, normalize only the URL host casing.
    try:
        p = urlsplit(raw)
        if p.scheme and p.netloc:
            raw = urlunsplit((p.scheme, p.netloc.lower(), p.path, p.query, p.fragment))
    except Exception:
        pass

    return f"{host}::{raw}"


def build_feed_context(entry: Any) -> dict[str, Any]:
    """
    Build the normalized placeholder dict used by TOML templates.

    This only prepares RSS/feed placeholders. Your bot/checker scripts can add
    Discord-specific placeholders after this, for example:
      ctx["role_mention"] = "<@&...>"
      ctx["global_mention"] = "@everyone"
      ctx["chapter_author_url"] = AUTHOR_URL
      ctx["button_label"] = "5"
      ctx["button_emoji"] = "<:mistmint_currency:1433046707121422487>"
    """
    pub_dt = parse_pub_datetime(entry)
    pub_raw = (
        getattr(entry, "published", None)
        or entry_get(entry, "published", "pubDate", "pub_date", default="")
    )

    featured_image = get_obj_url(entry, "featuredImage", "featuredimage", "featured_image")
    host_logo = get_obj_url(entry, "hostLogo", "hostlogo", "host_logo")
    comment_image = get_obj_url(entry, "commentImage", "commentimage", "comment_image")

    short_code = norm(entry_get(entry, "short_code", "shortcode", "shortCode", "short", default="")).upper()
    category = norm(entry_get(entry, "category", default=""))

    # dc:creator from feedparser can appear as author, dc_creator, or creator.
    creator = norm(entry_get(entry, "creator", "dc_creator", "author", default=""))
    author = norm(entry_get(entry, "author", "dc_creator", "creator", default=""))

    guid_is_permalink = entry_get(
        entry,
        "guid_is_permalink",
        "guidislink",
        "isPermaLink",
        "ispermalink",
        default="",
    )

    ctx: dict[str, Any] = {
        # Common RSS fields
        "title": norm(entry_get(entry, "title", default="")),
        "volume": norm(entry_get(entry, "volume", default="")),
        "chapter": norm(entry_get(entry, "chapter", default="")) or "New Chapter",
        "chaptername": norm(entry_get(entry, "chaptername", "chapter_name", default="")),
        "link": norm(entry_get(entry, "link", default="")),
        "description": norm(entry_get(entry, "description", default="")),
        "category": category,
        "translator": norm(entry_get(entry, "translator", default="")),
        "short_code": short_code,
        "coin": norm(entry_get(entry, "coin", default="")),

        # Image aliases from docs/rss-template-placeholders.md
        "featured_image": featured_image,
        "featured_image_url": featured_image,
        "host": norm(entry_get(entry, "host", default="")),
        "host_logo": host_logo,
        "host_logo_url": host_logo,
        "comment_image": comment_image,
        "comment_image_url": comment_image,

        # Date aliases
        "pub_date": norm(pub_raw),
        "pub_date_iso": pub_dt.isoformat() if pub_dt else "",
        "published": norm(pub_raw),
        "published_iso": pub_dt.isoformat() if pub_dt else "",

        # GUID aliases
        "guid": norm(entry_get(entry, "guid", "id", default="")),
        "id": norm(entry_get(entry, "id", "guid", default="")),
        "guid_is_permalink": norm(guid_is_permalink),

        # Comment feed fields
        "creator": creator,
        "author": author,
        "dc_creator": creator,
        "reply_chain": norm(entry_get(entry, "reply_chain", "replyChain", default="")),

        # Convenience booleans/aliases for *_when checks
        "is_nsfw": category.upper() == "NSFW",
    }

    return ctx
