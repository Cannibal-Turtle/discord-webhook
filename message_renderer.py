# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from config_loader import embed_color, load_toml

try:
    import discord
    from discord import Embed
    from discord.ui import Button, View
except Exception:
    # Allows raw-API-only scripts to import this file safely.
    discord = None
    Embed = None
    Button = None
    View = None


TEMPLATE_DIR = Path("message_templates")
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_\.]*)\}")

# Empty lists are important for allowed_mentions = { parse = [] }.
KEEP_EMPTY_KEYS = {"parse", "users", "roles", "allowed_mentions"}


def get_path(ctx: dict[str, Any], key: str, default: Any = "") -> Any:
    """Support placeholders like {title} and nested placeholders like {novel.url}."""
    cur: Any = ctx

    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]

    return cur


def is_truthy(ctx: dict[str, Any], key: str | None) -> bool:
    """
    Used by TOML conditions:
      description_when = "chaptername"
      when = "has_unlocked_arcs"
    """
    if not key:
        return True
    return bool(get_path(ctx, key, ""))


def render_text(value: Any, ctx: dict[str, Any]) -> Any:
    """Replace {placeholders}; unknown placeholders become empty strings."""
    if not isinstance(value, str):
        return value

    def repl(match: re.Match) -> str:
        replacement = get_path(ctx, match.group(1), "")
        return "" if replacement is None else str(replacement)

    return PLACEHOLDER_RE.sub(repl, value)


def should_drop(key: str, value: Any) -> bool:
    if key in KEEP_EMPTY_KEYS:
        return False
    return value in (None, "", {}, [])


def render_obj(obj: Any, ctx: dict[str, Any]) -> Any:
    """Recursively render strings/lists/dicts from TOML."""
    if isinstance(obj, str):
        return render_text(obj, ctx)

    if isinstance(obj, list):
        out = []
        for item in obj:
            rendered = render_obj(item, ctx)
            if rendered not in (None, "", {}, []):
                out.append(rendered)
        return out

    if isinstance(obj, dict):
        # Object-level conditional: when = "some_ctx_key"
        if not is_truthy(ctx, obj.get("when")):
            return None

        out: dict[str, Any] = {}

        for key, value in obj.items():
            if key == "when" or key.endswith("_when"):
                continue

            # Field-level conditional: description_when = "chaptername"
            condition_key = obj.get(f"{key}_when")
            if condition_key and not is_truthy(ctx, condition_key):
                continue

            if key == "color":
                # Supports:
                #   color = "free_chapter"
                #   color = { key = "free_chapter", default = "FFF9BF" }
                if isinstance(value, dict):
                    color_key = render_text(value.get("key", ""), ctx)
                    default = render_text(value.get("default", "000000"), ctx)
                else:
                    color_key = render_text(value, ctx)
                    default = "000000"

                out[key] = embed_color(
                    str(color_key),
                    str(default),
                    short_code=str(ctx.get("short_code", "")),
                    novel_color=str(
                        ctx.get("discord_color", "")
                        or ctx.get("theme_color", "")
                        or ctx.get("novel_color", "")
                    ),
                )
                continue

            rendered = render_obj(value, ctx)

            if should_drop(key, rendered):
                continue

            out[key] = rendered

        return out

    return obj


def load_template(name: str, *, variant: str | None = None) -> dict[str, Any]:
    """
    Load message_templates/{name}.toml.

    variant is for files like completed_novel.toml:
      [paid]
      content = "..."

      [free]
      content = "..."
    """
    data = load_toml(TEMPLATE_DIR / f"{name}.toml")

    if variant:
        if variant not in data:
            raise RuntimeError(f"Missing [{variant}] in message_templates/{name}.toml")
        return copy.deepcopy(data[variant])

    return copy.deepcopy(data)


def render_message(name: str, ctx: dict[str, Any], *, variant: str | None = None) -> dict[str, Any]:
    template = load_template(name, variant=variant)
    payload = render_obj(template, ctx) or {}

    # mode is template metadata, not a Discord payload field.
    payload.pop("mode", None)

    # Let TOML multiline strings stay readable without adding blank top/bottom lines.
    if isinstance(payload.get("content"), str):
        payload["content"] = payload["content"].strip("\n")

    # suppress_embeds is easier to write/read in TOML than flags = 4.
    if payload.pop("suppress_embeds", False):
        payload["flags"] = int(payload.get("flags", 0)) | 4

    return payload


def render_message_sequence(name: str, ctx: dict[str, Any], *, variant: str | None = None) -> list[dict[str, Any]]:
    """
    For multi-message templates like new_arcs.toml:

      [[messages]]
      name = "header"
      content = "..."

      [[messages]]
      name = "locked"
      content = "..."
    """
    template = load_template(name, variant=variant)
    messages = template.get("messages", [])

    rendered_messages: list[dict[str, Any]] = []

    for message in messages:
        rendered = render_obj(message, ctx)
        if not rendered:
            continue

        # Keep readable TOML multiline strings from adding blank top/bottom lines.
        if isinstance(rendered.get("content"), str):
            rendered["content"] = rendered["content"].strip("\n")

        # suppress_embeds is easier to write/read in TOML than flags = 4.
        if rendered.pop("suppress_embeds", False):
            rendered["flags"] = int(rendered.get("flags", 0)) | 4

        rendered_messages.append(rendered)

    return rendered_messages


def parse_custom_emoji(value: Any) -> Any:
    """Return discord.py PartialEmoji for <:name:id>, or unicode emoji string."""
    if value is None:
        return None

    s = str(value).strip()
    if not s:
        return None

    m = re.match(r"^<(?P<animated>a?):(?P<name>[A-Za-z0-9_]+):(?P<id>\d+)>$", s)
    if m and discord is not None:
        return discord.PartialEmoji(
            name=m.group("name"),
            id=int(m.group("id")),
            animated=bool(m.group("animated")),
        )

    # Unicode emoji / plain text emoji.
    return s


def api_emoji(value: Any) -> dict[str, Any] | None:
    """Return Discord API emoji object for buttons/components."""
    if value is None:
        return None

    s = str(value).strip()
    if not s:
        return None

    m = re.match(r"^<(?P<animated>a?):(?P<name>[A-Za-z0-9_]+):(?P<id>\d+)>$", s)
    if m:
        return {
            "name": m.group("name"),
            "id": m.group("id"),
            "animated": bool(m.group("animated")),
        }

    return {"name": s}


def button_style_value(style: Any) -> int:
    """Map readable TOML button styles to Discord API style numbers."""
    if isinstance(style, int):
        return style

    s = str(style or "link").strip().lower()
    return {
        "primary": 1,
        "secondary": 2,
        "success": 3,
        "danger": 4,
        "link": 5,
    }.get(s, 5)


def build_embed(data: dict[str, Any]) -> Any:
    """Convert a rendered embed dict into discord.Embed."""
    if Embed is None:
        raise RuntimeError("discord.py is not available, cannot build discord.Embed")

    data = dict(data)
    color = data.pop("color", None)

    embed = Embed(
        title=data.pop("title", None),
        url=data.pop("url", None),
        description=data.pop("description", None),
        color=color,
    )

    timestamp = data.pop("timestamp", None)
    if timestamp:
        from dateutil import parser as dateparser
        try:
            embed.timestamp = dateparser.parse(str(timestamp))
        except Exception:
            pass

    author = data.pop("author", None)
    if isinstance(author, dict) and author.get("name"):
        embed.set_author(**author)

    thumbnail = data.pop("thumbnail", None)
    if isinstance(thumbnail, dict) and thumbnail.get("url"):
        embed.set_thumbnail(url=thumbnail["url"])

    image = data.pop("image", None)
    if isinstance(image, dict) and image.get("url"):
        embed.set_image(url=image["url"])

    footer = data.pop("footer", None)
    if isinstance(footer, dict) and (footer.get("text") or footer.get("icon_url")):
        embed.set_footer(**footer)

    for field in data.pop("fields", []) or []:
        if not isinstance(field, dict):
            continue
        embed.add_field(
            name=field.get("name") or "\u200b",
            value=field.get("value") or "\u200b",
            inline=bool(field.get("inline", False)),
        )

    return embed


def build_view(components: Any) -> Any:
    """Convert rendered TOML components into a discord.ui.View for classic buttons."""
    if not components:
        return None
    if View is None or Button is None:
        raise RuntimeError("discord.py is not available, cannot build discord.ui.View")

    # Expected TOML shape:
    # [components]
    # [[components.action_rows]]
    # [[components.action_rows.buttons]]
    rows = []
    if isinstance(components, dict):
        rows = components.get("action_rows") or []
    elif isinstance(components, list):
        rows = components

    view = View()

    for row in rows:
        if not isinstance(row, dict):
            continue

        for button in row.get("buttons", []) or row.get("components", []) or []:
            if not isinstance(button, dict):
                continue

            style = str(button.get("style", "link")).strip().lower()

            # For now, only link buttons are safe/generic for your current scripts.
            if style != "link" and button_style_value(style) != 5:
                continue

            kwargs = {
                "label": button.get("label") or None,
                "url": button.get("url") or None,
            }

            emoji = parse_custom_emoji(button.get("emoji"))
            if emoji:
                kwargs["emoji"] = emoji

            if kwargs["url"]:
                view.add_item(Button(**kwargs))

    return view if view.children else None


def build_allowed_mentions(allowed_mentions: Any) -> Any:
    """Convert rendered allowed_mentions dict into discord.AllowedMentions."""
    if discord is None:
        raise RuntimeError("discord.py is not available, cannot build AllowedMentions")

    if not isinstance(allowed_mentions, dict):
        return None

    parse = set(allowed_mentions.get("parse") or [])

    users_value: bool | list[Any]
    roles_value: bool | list[Any]

    if "users" in parse:
        users_value = True
    else:
        users = [str(x).strip() for x in allowed_mentions.get("users", []) if str(x).strip()]
        users_value = [discord.Object(id=int(x)) for x in users] if users else False

    if "roles" in parse:
        roles_value = True
    else:
        roles = [str(x).strip() for x in allowed_mentions.get("roles", []) if str(x).strip()]
        roles_value = [discord.Object(id=int(x)) for x in roles] if roles else False

    return discord.AllowedMentions(
        everyone=("everyone" in parse),
        users=users_value,
        roles=roles_value,
        replied_user=bool(allowed_mentions.get("replied_user", False)),
    )


def to_discord_py_kwargs(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Convert rendered payload into kwargs for discord.py:
      await channel_or_thread.send(**kwargs)
    """
    kwargs: dict[str, Any] = {}

    if payload.get("content") not in (None, ""):
        kwargs["content"] = payload["content"]

    embeds_data = payload.get("embeds") or []
    embeds = [build_embed(e) for e in embeds_data if isinstance(e, dict)]

    if len(embeds) == 1:
        kwargs["embed"] = embeds[0]
    elif len(embeds) > 1:
        kwargs["embeds"] = embeds

    view = build_view(payload.get("components"))
    if view:
        kwargs["view"] = view

    allowed_mentions = build_allowed_mentions(payload.get("allowed_mentions"))
    if allowed_mentions is not None:
        kwargs["allowed_mentions"] = allowed_mentions

    if int(payload.get("flags", 0)) & 4:
        kwargs["suppress_embeds"] = True

    return kwargs


def api_components(components: Any) -> list[dict[str, Any]] | None:
    """Convert TOML component shape into Discord API component JSON."""
    if not components:
        return None

    rows = []
    if isinstance(components, dict):
        rows = components.get("action_rows") or []
    elif isinstance(components, list):
        rows = components

    api_rows: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        api_buttons: list[dict[str, Any]] = []
        for button in row.get("buttons", []) or row.get("components", []) or []:
            if not isinstance(button, dict):
                continue

            style = button_style_value(button.get("style", "link"))
            b: dict[str, Any] = {
                "type": 2,
                "style": style,
            }

            if button.get("label"):
                b["label"] = button["label"]

            emoji = api_emoji(button.get("emoji"))
            if emoji:
                b["emoji"] = emoji

            if style == 5:
                if not button.get("url"):
                    continue
                b["url"] = button["url"]
            else:
                # Non-link buttons need custom_id. Keep this generic for future use.
                b["custom_id"] = button.get("custom_id") or button.get("id") or "template_button"

            if "disabled" in button:
                b["disabled"] = bool(button["disabled"])

            api_buttons.append(b)

        if api_buttons:
            api_rows.append({"type": 1, "components": api_buttons})

    return api_rows or None


def to_discord_api_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Convert rendered payload into raw Discord API JSON.

    Use this for scripts that post with requests/aiohttp:
      payload = to_discord_api_payload(render_message(...))
      requests.post(url, headers=headers, json=payload)
    """
    out = copy.deepcopy(payload)

    components = api_components(out.pop("components", None))
    if components:
        out["components"] = components

    # Keep only valid top-level JSON payload-ish keys.
    allowed = {
        "content",
        "embeds",
        "components",
        "allowed_mentions",
        "flags",
        "tts",
        "message_reference",
    }

    return {k: v for k, v in out.items() if k in allowed and v not in (None, "")}
