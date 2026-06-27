from __future__ import annotations

import html
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


def _entry_get(entry: Any, *keys: str, default: str = "") -> Any:
    for key in keys:
        variants = (key, key.lower(), key.upper())
        for variant in variants:
            try:
                value = entry.get(variant)
            except AttributeError:
                value = getattr(entry, variant, None)
            if value not in (None, ""):
                return value
    return default


def _normalize_raw_guid(raw: Any) -> str:
    raw = html.unescape(str(raw or "").strip())

    try:
        parsed = urlsplit(raw)
        if parsed.scheme and parsed.netloc:
            raw = urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc.lower(),
                    parsed.path,
                    parsed.query,
                    parsed.fragment,
                )
            )
    except Exception:
        pass

    return raw


def raw_guid_from_entry(entry: Any) -> str:
    return _normalize_raw_guid(_entry_get(entry, "guid", "id"))


def host_from_entry(entry: Any, default: str = "") -> str:
    return str(_entry_get(entry, "host", "Host", "HOST", default=default) or "").strip()


def short_code_from_entry(entry: Any) -> str:
    return str(
        _entry_get(
            entry,
            "short_code",
            "shortcode",
            "shortCode",
            "short",
            default="",
        )
        or ""
    ).strip().upper()


def guid_identity(value: Any) -> str:
    """
    Return the part used for duplicate checks.

    This deliberately understands all of these state formats:
      host::short_code::guid
      host::guid
      short_code::guid
      guid
    """
    value = _normalize_raw_guid(value)
    if "::" in value:
        value = value.rsplit("::", 1)[-1].strip()
    return _normalize_raw_guid(value)


def entry_guid_identity(entry: Any) -> str:
    return guid_identity(raw_guid_from_entry(entry))


def seen_guid_identities(items: Iterable[Any] | None) -> set[str]:
    out: set[str] = set()
    for item in items or []:
        ident = guid_identity(item)
        if ident:
            out.add(ident)
    return out


def format_seen_guid(entry: Any, *, default_host: str = "") -> str:
    """Format what gets saved in state_rss.json for human readability."""
    guid = entry_guid_identity(entry)
    if not guid:
        return ""

    host = host_from_entry(entry, default_host)
    short_code = short_code_from_entry(entry)

    parts = [part for part in (host, short_code, guid) if part]
    return "::".join(parts)
