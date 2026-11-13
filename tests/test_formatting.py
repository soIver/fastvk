from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from fastvk import Bot, ParseMode
from fastvk.formatting import (
    get_format_data_for_message,
    prepare_formatted_message_params,
)
from fastvk.methods import MessagesEdit, MessagesSend
from fastvk.types import CallbackQuery, Message


@pytest.mark.parametrize(
    ("text", "clean", "items"),
    [
        ("🔥 __Заказ__ и _срочно_", "🔥 Заказ и срочно", [
            {"type": "bold", "offset": 3, "length": 5},
            {"type": "italic", "offset": 11, "length": 6},
        ]),
        ("Обычный __текст", "Обычный __текст", []),
        ("@id123(Иван) __🔥__", "@id123(Иван) 🔥", [
            {"type": "bold", "offset": 5, "length": 2},
        ]),
        ("__@club1(Дом)__", "@club1(Дом)", [
            {"type": "bold", "offset": 0, "length": 3},
        ]),
    ],
)
def test_formatting_preserves_platform_rendering(text: str, clean: str, items: list[dict]) -> None:
    assert get_format_data_for_message(text) == ({"version": "1", "items": items}, clean)


@pytest.mark.parametrize("mode", ["markdown", "ParseMode.MARKDOWN", ParseMode.MARKDOWN])
def test_parameter_preparation_is_repeatable_and_preserves_content_source(mode: str) -> None:
    original = {"message": "__Text__", "parse_mode": mode, "content_source": '{"type":"message"}'}
    prepared = prepare_formatted_message_params("messages.edit", original)
    assert prepared["message"] == "Text"
    assert prepared["content_source"] == original["content_source"]
    assert original["message"] == "__Text__"
    assert "parse_mode" not in prepared
    assert prepare_formatted_message_params("messages.edit", prepared) == prepared


@pytest.mark.parametrize("method", ["messages.send", "messages.edit"])
def test_legacy_content_source_is_supported_only_for_message_methods(method: str) -> None:
    prepared = prepare_formatted_message_params(method, {"message": "__Text__", "content_source": "markdown"})
    assert prepared["message"] == "Text"
    assert "content_source" not in prepared
    assert prepare_formatted_message_params("wall.post", {"message": "__Text__"}) == {"message": "__Text__"}
    assert prepare_formatted_message_params(method, {"message": "__Text__"}) == {"message": "__Text__"}


@pytest.mark.parametrize("operation", ["dynamic", "typed", "emit", "answer", "reply", "edit", "callback"])
async def test_formatting_reaches_http_for_all_message_paths(
    operation: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = Bot(token="test-token")
    response = MagicMock()
    response.json = AsyncMock(return_value={"response": 1})
    session = MagicMock()
    session.post.return_value.__aenter__.return_value = response
    monkeypatch.setattr(bot, "_get_session", AsyncMock(return_value=session))
    message = Message.from_dict({"id": 100, "peer_id": 42, "from_id": 42, "date": 0}, bot)
    text = "🔥 __Заказ__"
    if operation == "dynamic":
        await bot.messages.send(peer_id=42, message=text, parse_mode=ParseMode.MARKDOWN)
    elif operation == "typed":
        await bot(MessagesSend(peer_id=42, message=text, parse_mode=ParseMode.MARKDOWN))
    elif operation == "emit":
        await MessagesEdit(peer_id=42, cmid=7, message=text, parse_mode="markdown").emit(bot)
    elif operation == "callback":
        callback = CallbackQuery(user_id=42, peer_id=42, event_id="click", conversation_message_id=7)
        callback._bot = bot
        await callback.edit_message(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await getattr(message, operation)(text, parse_mode=ParseMode.MARKDOWN)
    params = session.post.call_args.kwargs["data"]
    assert params["message"] == "🔥 Заказ"
    assert json.loads(params["format_data"])["items"] == [{"type": "bold", "offset": 3, "length": 5}]
    assert "parse_mode" not in params
    assert "content_source" not in params
