from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from fastvk import Bot, SentMessage, VKCall
from fastvk.exceptions import VKAPIError
from fastvk.test import MockedBot


async def test_send_returns_local_and_global_ids_and_replies_by_local_id() -> None:
    bot = MockedBot()
    bot.set_result("messages.send", [{"peer_id": 42, "message_id": 9000, "conversation_message_id": 7}])
    result = await bot.send_message(42, "Reply", reply_to_conversation_message_id=5, random_id=123)
    assert result == SentMessage(peer_id=42, conversation_message_id=7, message_id=9000)
    params = bot.assert_called("messages.send").params
    assert params["peer_ids"] == [42]
    assert "peer_id" not in params
    assert params["random_id"] == 123
    assert json.loads(params["forward"]) == {
        "peer_id": 42, "conversation_message_ids": [5], "is_reply": True,
    }
    assert "reply_to" not in params
    assert "disable_mentions" not in params


async def test_attachment_only_send_and_missing_global_id() -> None:
    bot = MockedBot()
    bot.set_result("messages.send", [{"conversation_message_id": 7}])
    assert await bot.send_message(42, attachment="photo-1_2") == SentMessage(42, 7)
    params = bot.assert_called("messages.send").params
    assert "message" not in params
    assert params["attachment"] == "photo-1_2"
    assert 0 < params["random_id"] < 2**31


@pytest.mark.parametrize("response", [
    9000, [], [{"message_id": 9000}], [{"conversation_message_id": 0}],
    [{"conversation_message_id": True}], [{"peer_id": 43, "conversation_message_id": 7}],
    [{"conversation_message_id": 7}, {"conversation_message_id": 8}],
])
async def test_send_does_not_guess_missing_local_id_or_wrong_recipient(response: object) -> None:
    bot = MockedBot()
    bot.set_result("messages.send", response)
    with pytest.raises(RuntimeError):
        await bot.send_message(42, "Text")


async def test_send_propagates_per_recipient_api_error() -> None:
    bot = MockedBot()
    bot.set_result("messages.send", [{"peer_id": 42, "error": {"error_code": 901, "error_msg": "Cannot send"}}])
    with pytest.raises(VKAPIError) as raised:
        await bot.send_message(42, "Text")
    assert raised.value.code == 901


@pytest.mark.parametrize("operation", ["edit", "delete"])
async def test_conversation_operations_use_canonical_wire_names(operation: str) -> None:
    bot = MockedBot()
    if operation == "edit":
        bot.set_result("messages.edit", 1)
        assert await bot.edit_message(42, 7, "__Text__", parse_mode="markdown", keep_forward_messages=1) == 1
        params = bot.assert_called("messages.edit").params
        assert params["message"] == "Text"
        assert params["cmid"] == 7
        assert params["keep_forward_messages"] == 1
        assert "disable_mentions" not in params
    else:
        bot.set_result("messages.delete", {"7": 1})
        assert await bot.delete_message(42, 7) == {"7": 1}
        params = bot.assert_called("messages.delete").params
        assert params["cmids"] == 7
        assert "delete_for_all" not in params
        assert "message_ids" not in params
    assert params["peer_id"] == 42
    assert "conversation_message_id" not in params
    assert "message_id" not in params


@pytest.mark.parametrize("cmid", [0, -1, True])
async def test_invalid_local_ids_fail_before_sending(cmid: int) -> None:
    bot = MockedBot()
    with pytest.raises(ValueError, match="conversation_message_id"):
        await bot.edit_message(42, cmid, "Text")
    with pytest.raises(ValueError, match="conversation_message_id"):
        await bot.delete_message(42, cmid)
    with pytest.raises(ValueError, match="conversation_message_id"):
        await bot.send_message(42, "Reply", reply_to_conversation_message_id=cmid)
    assert bot.calls == []


def test_factories_reject_conflicting_selectors() -> None:
    with pytest.raises(ValueError):
        VKCall.edit_message(42, 7, message_id=9000)
    with pytest.raises(ValueError):
        VKCall.delete_message(42, 7, message_id=9000)
    with pytest.raises(ValueError):
        VKCall.delete_message(42)
    with pytest.raises(ValueError):
        VKCall.delete_message(42, 7, cmids=8)
    with pytest.raises(ValueError):
        VKCall.send_message(42, peer_ids=[43])
    with pytest.raises(ValueError):
        VKCall.send_message(42, reply_to_conversation_message_id=7, reply_to=9000)
    assert VKCall.delete_message(42, message_id=9000).params["message_ids"] == 9000


async def test_factories_can_be_emitted_or_batched_without_changing_parameters() -> None:
    bot = MockedBot()
    call = VKCall.send_message(42, "__Text__", extended_result=True, parse_mode="markdown", random_id=123)
    await call.emit(bot)
    direct = bot.assert_called("messages.send").params
    bot.set_result("execute", {"response": [[{"conversation_message_id": 7}]]})
    result = await bot.execute_batch_detailed([call])
    params = bot.assert_called("execute").params
    assert all(params[f"call_0_{key}"] == value for key, value in direct.items())
    assert SentMessage.from_response(result[0].value, 42).conversation_message_id == 7


async def test_send_retry_keeps_random_id(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = Bot("test-token", retry_delay=0)
    response = MagicMock()
    response.json = AsyncMock(side_effect=[
        {"error": {"error_code": 6, "error_msg": "Try again"}},
        {"response": [{"peer_id": 42, "conversation_message_id": 7}]},
    ])
    session = MagicMock()
    session.post.return_value.__aenter__.return_value = response
    monkeypatch.setattr(bot, "_get_session", AsyncMock(return_value=session))
    monkeypatch.setattr("fastvk.api.client.asyncio.sleep", AsyncMock())
    assert (await bot.send_message(42, "Text")).conversation_message_id == 7
    first, second = session.post.call_args_list
    assert first.kwargs["data"]["random_id"] == second.kwargs["data"]["random_id"]
