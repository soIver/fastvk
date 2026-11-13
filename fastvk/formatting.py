from __future__ import annotations

import json
import re
from typing import Any

_MARKDOWN_PATTERN = re.compile(r"__(.+?)__|_(.+?)_")
_VK_MENTION_PATTERN = re.compile(r"@(?:id|club)\d+\(([^)\n]+)\)")
_MARKDOWN_PARSE_MODES = frozenset({"markdown", "parsemode.markdown"})
_FORMATTED_MESSAGE_METHODS = frozenset({"messages.send", "messages.edit"})


def _utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _rendered_utf16_length(value: str) -> int:
    length = 0
    cursor = 0
    for match in _VK_MENTION_PATTERN.finditer(value):
        length += _utf16_length(value[cursor : match.start()])
        length += _utf16_length(match.group(1))
        cursor = match.end()
    return length + _utf16_length(value[cursor:])


def get_format_data_for_message(message_text: str) -> tuple[dict[str, Any], str]:
    clean_parts: list[str] = []
    items: list[dict[str, int | str]] = []
    offset = 0
    cursor = 0

    for match in _MARKDOWN_PATTERN.finditer(message_text):
        start, end = match.span()
        if cursor < start:
            plain_text = message_text[cursor:start]
            clean_parts.append(plain_text)
            offset += _rendered_utf16_length(plain_text)

        if match.group(1) is not None:
            format_type = "bold"
            formatted_text = match.group(1)
        else:
            format_type = "italic"
            formatted_text = match.group(2)

        clean_parts.append(formatted_text)
        items.append(
            {
                "type": format_type,
                "offset": offset,
                "length": _rendered_utf16_length(formatted_text),
            },
        )
        offset += _rendered_utf16_length(formatted_text)
        cursor = end

    if cursor < len(message_text):
        clean_parts.append(message_text[cursor:])

    return {"version": "1", "items": items}, "".join(clean_parts)


def _is_markdown_parse_mode(value: Any) -> bool:
    if value is None:
        return False
    normalized = getattr(value, "value", value)
    return str(normalized).lower() in _MARKDOWN_PARSE_MODES


def prepare_formatted_message_params(
    method: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    prepared = dict(params)
    if method not in _FORMATTED_MESSAGE_METHODS:
        return prepared
    parse_mode = prepared.pop("parse_mode", None)
    content_source = prepared.get("content_source")
    content_source_is_markdown = _is_markdown_parse_mode(content_source)
    markdown_enabled = (
        _is_markdown_parse_mode(parse_mode)
        or content_source_is_markdown
    )

    if content_source_is_markdown:
        prepared.pop("content_source", None)

    if not markdown_enabled:
        return prepared

    message_text = prepared.get("message")
    if not isinstance(message_text, str):
        return prepared

    format_data, clean_text = get_format_data_for_message(message_text)
    prepared["message"] = clean_text
    prepared["format_data"] = json.dumps(format_data, separators=(",", ":"))
    return prepared
