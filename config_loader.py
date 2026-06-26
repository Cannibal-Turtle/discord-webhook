# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

BASE_DIR = Path(__file__).resolve().parent


def repo_path(relative_path: str | Path) -> Path:
    path = Path(relative_path)
    return path if path.is_absolute() else BASE_DIR / path


def load_toml(relative_path: str | Path, *, required: bool = True, default: Any = None) -> Any:
    path = repo_path(relative_path)

    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if required:
            raise RuntimeError(f"Missing required TOML config file: {relative_path}")
        return {} if default is None else default


def load_json(relative_path: str | Path, *, required: bool = True, default: Any = None) -> Any:
    path = repo_path(relative_path)

    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        if required:
            raise RuntimeError(f"Missing required config file: {relative_path}")
        return {} if default is None else default
    except json.JSONDecodeError as e:
        if required:
            raise RuntimeError(f"Invalid JSON in required config file {relative_path}: {e}")
        return {} if default is None else default


FILES = load_json("config/files.json")
FEEDS = load_json("config/feeds.json")
ROLES = load_json("config/roles.json")
EMBEDS = load_json("config/embeds.json", required=False, default={})
SERVER = load_json("config/server.json")


def require_value(source: dict, key: str, label: str) -> Any:
    value = source.get(key)
    if value in (None, ""):
        raise RuntimeError(f"Missing required config value: {label}.{key}")
    return value


def require_file_value(key: str) -> Any:
    return require_value(FILES, key, "files")


def require_feeds_value(key: str) -> Any:
    return require_value(FEEDS, key, "feeds")


def require_feed_value(feed_name: str, key: str) -> Any:
    feed = FEEDS.get(feed_name)
    if not isinstance(feed, dict):
        raise RuntimeError(f"Missing required feed config: feeds.{feed_name}")
    return require_value(feed, key, f"feeds.{feed_name}")


def require_feed_url(feed_name: str) -> str:
    feed_key = require_feed_value(feed_name, "feed_key")

    try:
        from novel_mappings import get_output_feed_url
    except Exception as e:
        raise RuntimeError(
            "Could not import get_output_feed_url from rss-feed/novel_mappings. "
            "Make sure the latest rss-feed package is installed."
        ) from e

    url = get_output_feed_url(feed_key)

    if not url:
        raise RuntimeError(
            f"Missing output feed URL for {feed_key!r}. "
            "Check rss-feed/mappings/output_feeds.toml."
        )

    return url


def require_role_value(key: str) -> Any:
    return require_value(ROLES, key, "roles")


def require_server_value(key: str) -> Any:
    return require_value(SERVER, key, "server")


def server_channel_id(key: str) -> int:
    return int(require_server_value(key))


def server_channel_id_str(key: str) -> str:
    return str(require_server_value(key)).strip()


def server_guild_id() -> str:
    return str(require_server_value("guild_id")).strip()


def embed_value(key: str, default: Any = None) -> Any:
    return EMBEDS.get(key, default)


def require_embed_value(key: str) -> Any:
    return require_value(EMBEDS, key, "embeds")

def embed_color_hex(key: str, default: str) -> str:
    colors = EMBEDS.get("colors", {})

    if isinstance(colors, dict):
        value = colors.get(key)
    else:
        value = None

    value = value or EMBEDS.get(key) or default
    return str(value).strip().lstrip("#")


def get_novel_color_from_short_code(short_code: str) -> str:
    """
    Returns the novel's theme/Discord color from rss-feed mappings.

    Looks for:
      theme_color
      discord_color

    Returns "" if not found.
    """
    short_code = (short_code or "").strip().upper()

    if not short_code:
        return ""

    try:
        from novel_mappings import get_novel_details_by_short_code
    except Exception:
        return ""

    try:
        _host, _title, details = get_novel_details_by_short_code(short_code)
    except Exception:
        return ""

    if not details:
        return ""

    return str(
        details.get("theme_color")
        or details.get("discord_color")
        or ""
    ).strip()


def embed_color(
    key: str,
    default: str,
    *,
    short_code: str = "",
    novel_color: str = "",
) -> int:
    """
    Resolves an embed color.

    Supports fixed hex config:
      "paid_chapter": "A87676"

    Supports novel-specific config:
      "paid_chapter": "novel"

    In "novel" mode, it uses:
      1. explicit novel_color if passed
      2. theme_color / discord_color from rss-feed using short_code
      3. default fallback
    """
    configured = embed_color_hex(key, default)
    configured_key = str(configured or "").strip().casefold()

    if configured_key in {"novel", "theme", "theme_color", "discord_color"}:
        configured = (
            novel_color
            or get_novel_color_from_short_code(short_code)
            or default
        )

    configured = str(configured or default).strip().lstrip("#")
    return int(configured, 16)


def role_id_to_mention(role_id: str) -> str:
    role_id = str(role_id or "").strip()

    if not role_id:
        return ""

    if role_id.startswith("||") and role_id.endswith("||"):
        return role_id

    if role_id.startswith("<@&") and role_id.endswith(">"):
        return role_id

    return f"<@&{role_id}>"


def load_novel_discord_map(path: str | Path | None = None) -> dict:
    path = path or require_file_value("novel_discord_map_file")
    raw = load_toml(path)

    out = {}

    for short_code, value in raw.items():
        code = str(short_code).strip().upper()

        if not code:
            continue

        if not isinstance(value, dict):
            raise RuntimeError(
                f"Invalid novel Discord config for {code}: expected table"
            )

        out[code] = {
            "role_id": str(value.get("role_id", "")).strip(),
            "custom_emoji": str(value.get("custom_emoji", "")).strip(),
            "role_url": str(value.get("role_url", "")).strip(),
        }

    return out


def get_novel_discord_config(short_code: str) -> dict:
    short_code = (short_code or "").strip().upper()
    return NOVEL_DISCORD_MAP.get(short_code, {})


def get_novel_role_id(short_code: str) -> str:
    return get_novel_discord_config(short_code).get("role_id", "")


def get_novel_role_mention(short_code: str) -> str:
    return role_id_to_mention(get_novel_role_id(short_code))


def get_novel_custom_emoji(short_code: str) -> str:
    return get_novel_discord_config(short_code).get("custom_emoji", "")


def get_novel_role_url(short_code: str) -> str:
    return get_novel_discord_config(short_code).get("role_url", "")


def normalize_tag_key(tag: str) -> str:
    return " ".join(str(tag).strip().casefold().split())


def load_tag_role_map(path: str | Path | None = None) -> dict:
    path = path or require_file_value("tag_role_map_file")
    raw = load_json(path)

    return {
        normalize_tag_key(tag): str(role_id).strip()
        for tag, role_id in raw.items()
        if str(tag).strip() and str(role_id).strip()
    }


NOVEL_DISCORD_MAP = load_novel_discord_map()
TAG_ROLE_MAP = load_tag_role_map()
