# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent


def repo_path(relative_path: str | Path) -> Path:
    path = Path(relative_path)
    return path if path.is_absolute() else BASE_DIR / path


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


def require_role_value(key: str) -> Any:
    return require_value(ROLES, key, "roles")


def embed_value(key: str, default: Any = None) -> Any:
    return EMBEDS.get(key, default)


def require_embed_value(key: str) -> Any:
    return require_value(EMBEDS, key, "embeds")


def role_id_to_mention(role_id: str) -> str:
    role_id = str(role_id or "").strip()

    if not role_id:
        return ""

    if role_id.startswith("||") and role_id.endswith("||"):
        return role_id

    if role_id.startswith("<@&") and role_id.endswith(">"):
        return role_id

    return f"<@&{role_id}>"


def normalize_tag_key(tag: str) -> str:
    return " ".join(str(tag).strip().casefold().split())


def load_short_code_role_map(path: str | Path | None = None) -> dict:
    path = path or require_file_value("novel_role_id_map_file")
    raw = load_json(path)

    return {
        str(short_code).strip().upper(): str(role_id).strip()
        for short_code, role_id in raw.items()
        if str(short_code).strip() and str(role_id).strip()
    }


def load_tag_role_map(path: str | Path | None = None) -> dict:
    path = path or require_file_value("tag_role_map_file")
    raw = load_json(path)

    return {
        normalize_tag_key(tag): str(role_id).strip()
        for tag, role_id in raw.items()
        if str(tag).strip() and str(role_id).strip()
    }


NOVEL_ROLE_ID_MAP = load_short_code_role_map()
TAG_ROLE_MAP = load_tag_role_map()
