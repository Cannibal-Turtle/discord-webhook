#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe smoke healthcheck for this Discord bot repo.

It does not post to Discord and does not require real Discord/GitHub secrets.
It checks config parsing, Python syntax, workflow script paths, message template
rendering, state/config shape, and local env ignore safety.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.dont_write_bytecode = True

from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and below
    import tomli as tomllib  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
TEMPLATE_DIR = ROOT / "message_templates"
WORKFLOW_DIR = ROOT / ".github" / "workflows"
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
SNOWFLAKE_RE = re.compile(r"^\d{15,25}$")


class Healthcheck:
    def __init__(self) -> None:
        self.ok_count = 0
        self.warnings: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.current_section = "general"
        self.sections: dict[str, dict[str, int]] = {}

    def section(self, name: str) -> None:
        self.current_section = name
        self.sections.setdefault(name, {"ok": 0, "warnings": 0, "errors": 0})

    def _bump(self, kind: str) -> None:
        self.sections.setdefault(self.current_section, {"ok": 0, "warnings": 0, "errors": 0})
        self.sections[self.current_section][kind] += 1

    def ok(self, title: str, message: str = "") -> None:
        self.ok_count += 1
        self._bump("ok")
        print(f"✅ {title}: {message}" if message else f"✅ {title}")

    def warn(self, title: str, message: str = "") -> None:
        self.warnings.append({"section": self.current_section, "title": title, "message": message})
        self._bump("warnings")
        print(f"⚠️  {title}: {message}" if message else f"⚠️  {title}")

    def error(self, title: str, message: str = "") -> None:
        self.errors.append({"section": self.current_section, "title": title, "message": message})
        self._bump("errors")
        print(f"❌ {title}: {message}" if message else f"❌ {title}")

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok_count,
            "warning_count": len(self.warnings),
            "error_count": len(self.errors),
            "warnings": self.warnings,
            "errors": self.errors,
            "sections": self.sections,
        }


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else {}


def _read_toml(path: Path) -> dict[str, Any] | None:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else {}


def _iter_repo_files(pattern: str) -> list[Path]:
    files: list[Path] = []
    for path in sorted(ROOT.rglob(pattern)):
        parts = path.relative_to(ROOT).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        files.append(path)
    return files


def _is_snowflake(value: Any) -> bool:
    return bool(SNOWFLAKE_RE.fullmatch(str(value or "").strip()))


def _require_snowflake(hc: Healthcheck, label: str, value: Any) -> None:
    if _is_snowflake(value):
        hc.ok("snowflake", f"{label} looks valid")
    else:
        hc.error("snowflake", f"{label} should be a Discord ID string")


def _repo_kind() -> str:
    if (CONFIG_DIR / "thread_id_map.json").exists():
        return "mistmint-discord"
    if (CONFIG_DIR / "novel_discord_map.toml").exists():
        return "discord-webhook"
    return ROOT.name


def check_parse_files(hc: Healthcheck) -> None:
    hc.section("parse")
    for path in _iter_repo_files("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
            hc.ok("json parse", _rel(path))
        except Exception as exc:
            hc.error("json parse", f"{_rel(path)}: {exc}")

    for path in _iter_repo_files("*.toml"):
        try:
            tomllib.loads(path.read_text(encoding="utf-8"))
            hc.ok("toml parse", _rel(path))
        except Exception as exc:
            hc.error("toml parse", f"{_rel(path)}: {exc}")


def check_python_syntax(hc: Healthcheck) -> None:
    hc.section("python")
    for path in _iter_repo_files("*.py"):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
            hc.ok("python syntax", _rel(path))
        except Exception as exc:
            hc.error("python syntax", f"{_rel(path)}: {exc}")


def check_gitignore_and_cache(hc: Healthcheck) -> None:
    hc.section("gitignore")
    path = ROOT / ".gitignore"
    if not path.exists():
        hc.warn("gitignore", ".gitignore is missing")
        text = ""
    else:
        text = path.read_text(encoding="utf-8")
        if "__pycache__/" in text:
            hc.ok("gitignore", "__pycache__/ ignored")
        else:
            hc.warn("gitignore", "add __pycache__/")

        if "*.py[cod]" in text or "*.pyc" in text:
            hc.ok("gitignore", "compiled Python files ignored")
        else:
            hc.warn("gitignore", "add *.py[cod]")

        if ".env.*" in text and "!.env.example" in text:
            hc.ok("gitignore", ".env.local-style files ignored, .env.example allowed")
        else:
            hc.warn("gitignore", "add .env, .env.*, and !.env.example")

    env_local = ROOT / ".env.local"
    if env_local.exists():
        try:
            env_text = env_local.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            env_text = ""
        if "DISCORD_BOT_TOKEN=" in env_text or "PAT_GITHUB=" in env_text or "MISTMINT_COOKIE=" in env_text:
            hc.error("local env", ".env.local appears to contain real secrets; use ENV_FILE=... pointer instead")
        elif "ENV_FILE=" in env_text:
            hc.ok("local env", ".env.local is a pointer file")
        else:
            hc.warn("local env", ".env.local exists but is not an ENV_FILE pointer")
    else:
        hc.ok("local env", ".env.local not present in this checkout")

    caches = [p for p in ROOT.rglob("__pycache__") if ".git" not in p.parts]
    pycs = [p for p in ROOT.rglob("*.pyc") if ".git" not in p.parts]
    if caches or pycs:
        hc.warn("python cache files", f"found {len(caches)} __pycache__ folder(s) and {len(pycs)} .pyc file(s)")
    else:
        hc.ok("python cache files", "no __pycache__/.pyc files found")


def check_required_configs(hc: Healthcheck) -> None:
    hc.section("config")
    kind = _repo_kind()
    required = [
        "config/server.json",
        "config/feeds.json",
        "config/files.json",
        "config/embeds.json",
    ]
    if kind == "discord-webhook":
        required.extend([
            "config/roles.json",
            "config/novel_discord_map.toml",
            "config/tag_roles.json",
        ])
    elif kind == "mistmint-discord":
        required.append("config/thread_id_map.json")

    for rel in required:
        if (ROOT / rel).exists():
            hc.ok("required config", rel)
        else:
            hc.error("required config", f"missing {rel}")

    feeds = _read_json(CONFIG_DIR / "feeds.json") or {}
    for feed_name in ("free", "paid", "comments"):
        section = _as_dict(feeds.get(feed_name))
        if not section:
            hc.error("feeds", f"feeds.{feed_name} missing")
            continue
        for key in ("feed_key", "last_guid_key", "seen_key", "last_post_time_key"):
            if str(section.get(key) or "").strip():
                hc.ok("feeds", f"{feed_name}.{key} configured")
            else:
                hc.error("feeds", f"{feed_name}.{key} missing")

    try:
        seen_cap = int(feeds.get("seen_cap") or 0)
        if seen_cap > 0:
            hc.ok("feeds", f"seen_cap = {seen_cap}")
        else:
            hc.error("feeds", "seen_cap must be > 0")
    except Exception:
        hc.error("feeds", "seen_cap must be an integer")


def check_discord_ids(hc: Healthcheck) -> None:
    hc.section("discord ids")
    kind = _repo_kind()
    server = _read_json(CONFIG_DIR / "server.json") or {}

    if kind == "discord-webhook":
        for key in ("guild_id", "free_chapters", "paid_chapters", "comments", "announcements", "mod", "novel_cards_archive"):
            if key in server:
                _require_snowflake(hc, f"server.{key}", server.get(key))
            else:
                hc.warn("server", f"server.{key} missing")

        roles = _read_json(CONFIG_DIR / "roles.json") or {}
        for key, value in sorted(roles.items()):
            _require_snowflake(hc, f"roles.{key}", value)

        tag_roles = _read_json(CONFIG_DIR / "tag_roles.json") or {}
        for key, value in sorted(tag_roles.items()):
            _require_snowflake(hc, f"tag_roles.{key}", value)

        novel_map = _read_toml(CONFIG_DIR / "novel_discord_map.toml") or {}
        for code, section_value in sorted(novel_map.items()):
            section = _as_dict(section_value)
            role_id = section.get("role_id")
            if role_id:
                _require_snowflake(hc, f"novel_discord_map.{code}.role_id", role_id)
            else:
                hc.warn("novel map", f"{code}: role_id missing")
            if str(section.get("custom_emoji") or "").strip():
                hc.ok("novel map", f"{code}: custom_emoji configured")
            else:
                hc.warn("novel map", f"{code}: custom_emoji missing")
    elif kind == "mistmint-discord":
        for key in ("guild_id", "novel_cards_archive", "ping_user_id"):
            if key in server:
                _require_snowflake(hc, f"server.{key}", server.get(key))
            else:
                hc.warn("server", f"server.{key} missing")

        thread_map = _read_json(CONFIG_DIR / "thread_id_map.json") or {}
        if not thread_map:
            hc.warn("thread map", "config/thread_id_map.json has no entries")
        for code, thread_id in sorted(thread_map.items()):
            _require_snowflake(hc, f"thread_id_map.{code}", thread_id)


def check_mapping_history_consistency(hc: Healthcheck) -> None:
    hc.section("mapping consistency")
    kind = _repo_kind()
    history_codes = {p.stem.replace("_history", "").upper() for p in (ROOT / "arc_history").glob("*_history.json")}
    if not history_codes:
        hc.warn("arc history", "no arc_history/*_history.json files found")
        return
    hc.ok("arc history", f"{len(history_codes)} history file(s)")

    if kind == "discord-webhook":
        novel_map = _read_toml(CONFIG_DIR / "novel_discord_map.toml") or {}
        map_codes = {str(code).upper() for code in novel_map}
        missing = sorted(history_codes - map_codes)
        if missing:
            hc.warn("novel map", f"history code(s) missing from novel_discord_map: {', '.join(missing)}")
        else:
            hc.ok("novel map", "all arc_history codes have novel_discord_map entries")
    elif kind == "mistmint-discord":
        thread_map = _read_json(CONFIG_DIR / "thread_id_map.json") or {}
        map_codes = {str(code).upper() for code in thread_map}
        missing = sorted(history_codes - map_codes)
        if missing:
            hc.warn("thread map", f"history code(s) missing from thread_id_map: {', '.join(missing)}")
        else:
            hc.ok("thread map", "all arc_history codes have thread_id_map entries")


def check_workflow_script_paths(hc: Healthcheck) -> None:
    hc.section("workflows")
    if not WORKFLOW_DIR.exists():
        hc.warn("workflows", ".github/workflows missing")
        return

    script_re = re.compile(r"(?:^|\s)python(?:\s+-u)?\s+([A-Za-z0-9_./-]+\.py)\b")
    count = 0
    for path in sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        if "DISCORD_BOT_TOKEN" in text:
            hc.ok("workflow secret", f"{_rel(path)} uses DISCORD_BOT_TOKEN")
        for match in script_re.finditer(text):
            script = match.group(1)
            count += 1
            if (ROOT / script).exists():
                hc.ok("workflow script", f"{_rel(path)} → {script}")
            else:
                hc.error("workflow script", f"{_rel(path)} references missing {script}")
    if not count:
        hc.warn("workflow script", "no python script references found in workflows")


def _sample_ctx() -> dict[str, Any]:
    return {
        "title": "Example Novel",
        "novel_title": "Example Novel",
        "volume": "Arc 1",
        "chapter": "Chapter 1",
        "chaptername": "Example Chapter",
        "link": "https://example.com/chapter",
        "description": "Example description.",
        "category": "SFW",
        "translator": "CannibalTurtle",
        "translator_url": "https://example.com/@CannibalTurtle",
        "short_code": "EX",
        "featured_image": "https://example.com/cover.png",
        "featured_image_url": "https://example.com/cover.png",
        "pub_date": "Mon, 29 Jun 2026 05:00:00 GMT",
        "host": "Mistmint Haven",
        "host_logo": "https://example.com/logo.png",
        "host_logo_url": "https://example.com/logo.png",
        "guid": "example-guid",
        "guid_is_permalink": "false",
        "global_mention": "||<@&123456789012345678>||",
        "role_mention": "<@&123456789012345678>",
        "novel_role_mention": "<@&123456789012345678>",
        "discord_color": "#C9D3FF",
        "embed_color": "#C9D3FF",
        "timestamp": "2026-06-29T00:00:00+00:00",
        "discord_time": "<t:1893456000:F>",
        "button_label": "Read Now",
        "button_url": "https://example.com/read",
        "button_emoji": "📖",
        "links_text": "[Read](https://example.com)",
        "status_text": "Ongoing",
        "chapter_count": "20",
        "chapter_text": "Chapter 1-20",
        "chapter_link": "https://example.com/novel",
        "duration": "1 day",
        "has_unlocked_arcs": True,
        "unlocked_arcs_text": "Arc 1",
        "locked_arcs_text": "Arc 2",
        "current_arc": "Arc 1",
        "previous_arc": "Prologue",
        "arc_title": "Arc 1",
        "arc_name": "Arc 1",
        "extra_title": "Extra 1",
        "extra_name": "Extra 1",
    }


def check_templates(hc: Healthcheck) -> None:
    hc.section("templates")
    if not TEMPLATE_DIR.exists():
        hc.error("templates", "message_templates directory missing")
        return

    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        os.chdir(ROOT)
        from message_renderer import render_message, render_message_sequence, to_discord_api_payload
    except Exception as exc:
        hc.error("template import", f"could not import message_renderer: {exc}")
        return

    payload_keys = {"content", "embeds", "components", "allowed_mentions", "flags", "mode", "messages", "suppress_embeds"}
    ctx = _sample_ctx()

    for path in sorted(TEMPLATE_DIR.glob("*.toml")):
        name = path.stem
        data = _read_toml(path) or {}
        if not data:
            hc.warn("template", f"{name}: empty or unreadable")
            continue

        if not (set(data) & payload_keys) and all(isinstance(v, dict) for v in data.values()):
            variants: list[str | None] = list(data.keys())
        else:
            variants = [None]

        for variant in variants:
            label = f"{name}[{variant}]" if variant else name
            section = _as_dict(data.get(variant)) if variant else data
            try:
                if "messages" in section:
                    payloads = render_message_sequence(name, ctx, variant=variant)
                    if payloads:
                        hc.ok("template render", f"{label}: {len(payloads)} message(s)")
                    else:
                        hc.warn("template render", f"{label}: rendered no messages")
                else:
                    payload = to_discord_api_payload(render_message(name, ctx, variant=variant))
                    if payload.get("content") or payload.get("embeds") or payload.get("components"):
                        hc.ok("template render", f"{label}: payload ok")
                    else:
                        hc.error("template render", f"{label}: empty Discord payload")
            except Exception as exc:
                hc.error("template render", f"{label}: {exc}")


def run_all_checks(*, include_python: bool = True) -> Healthcheck:
    hc = Healthcheck()
    hc.section("repo")
    hc.ok("repo kind", _repo_kind())
    check_parse_files(hc)
    if include_python:
        check_python_syntax(hc)
    check_gitignore_and_cache(hc)
    check_required_configs(hc)
    check_discord_ids(hc)
    check_mapping_history_consistency(hc)
    check_workflow_script_paths(hc)
    check_templates(hc)
    return hc


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Discord bot repo config, templates, workflows, and local env safety.")
    parser.add_argument("--no-python", action="store_true", help="Skip Python syntax checks.")
    args = parser.parse_args()

    hc = run_all_checks(include_python=not args.no_python)
    summary = hc.summary()
    print("\n=== Healthcheck summary ===")
    print(f"OK: {summary['ok']}")
    print(f"Warnings: {summary['warning_count']}")
    print(f"Errors: {summary['error_count']}")
    return 1 if summary["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
