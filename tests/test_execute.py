from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from fastvk import Bot, VKCall, VKCallResult
from fastvk.execute import build_execute_batch, parse_execute_results
from fastvk.test import MockedBot


async def test_detailed_execute_keeps_nested_errors_without_replaying_successes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = Bot("test-token")
    payload = {
        "response": [1, False, 2],
        "execute_errors": [{"error_code": 6, "error_msg": "Rate limit", "method": "messages.edit"}],
    }
    response = MagicMock()
    response.json = AsyncMock(return_value=payload)
    session = MagicMock()
    session.post.return_value.__aenter__.return_value = response
    monkeypatch.setattr(bot, "_get_session", AsyncMock(return_value=session))
    assert await bot.execute_detailed("return Args.value;", value=42) == payload
    session.post.assert_called_once()
    assert session.post.call_args.kwargs["data"]["value"] == 42
    assert await bot.execute("return Args.value;", value=42) == payload["response"]


def test_results_pair_errors_only_with_false_and_preserve_successful_empty_values() -> None:
    results = parse_execute_results({
        "response": [0, [], False, 5, False],
        "execute_errors": [
            {"error_code": 100, "error_msg": "Bad request", "method": "messages.edit",
             "request_params": [{"key": "cmid", "value": "7"}]},
            {"error_code": 901, "error_msg": "Cannot send"},
        ],
    }, 5)
    assert [item.succeeded for item in results] == [True, True, False, True, False]
    assert results[2].error is not None
    assert results[2].error.code == 100
    assert results[2].error.method == "messages.edit"
    assert results[2].error.request_params == ({"key": "cmid", "value": "7"},)
    assert results[4].error is not None
    assert results[4].error.code == 901


def test_missing_results_are_failures_and_extra_results_are_ignored() -> None:
    assert parse_execute_results({"response": [1]}, 3) == [
        VKCallResult(1), VKCallResult(False), VKCallResult(False),
    ]
    assert parse_execute_results({"response": [1, 2]}, 1) == [VKCallResult(1)]
    assert parse_execute_results({"response": None}, 1) == [VKCallResult(False)]


async def test_detailed_batches_split_at_25_and_keep_order() -> None:
    bot = MockedBot()
    responses = iter([{"response": list(range(25))}, {"response": [25, 26]}])
    bot.set_result("execute", lambda: next(responses))
    results = await bot.execute_batch_detailed([VKCall("users.get", {"user_ids": i}) for i in range(27)])
    assert [item.value for item in results] == list(range(27))
    assert len(bot.calls) == 2
    assert bot.calls[0].params["call_24_user_ids"] == 24
    assert bot.calls[1].params["call_0_user_ids"] == 25


async def test_empty_batches_do_not_make_requests() -> None:
    bot = MockedBot()
    assert await bot.execute_batch([]) == []
    assert await bot.execute_batch_detailed([]) == []
    assert bot.calls == []


async def test_all_batches_are_validated_before_first_request() -> None:
    bot = MockedBot()
    calls = [("users.get", {})] * 25 + [("users.get);return [];", {})]
    with pytest.raises(ValueError, match="method"):
        await bot.execute_batch_detailed(calls)
    assert bot.calls == []
    with pytest.raises(ValueError, match="parameter"):
        await bot.execute_batch_detailed([("users.get", {"bad-key": 1})])
    assert bot.calls == []


def test_batch_values_are_arguments_and_share_message_formatting() -> None:
    text = '__Text__ "quoted"; return [];\n🔥'
    code, arguments = build_execute_batch([
        VKCall("messages.edit", {"peer_id": 42, "cmid": 7, "message": text,
                                 "parse_mode": "markdown", "attachment": None}),
    ])
    assert text not in code
    assert "Args.call_0_message" in code
    assert arguments["call_0_message"] == 'Text "quoted"; return [];\n🔥'
    assert json.loads(arguments["call_0_format_data"])["items"] == [
        {"type": "bold", "offset": 0, "length": 4},
    ]
    assert "parse_mode" not in code
    assert "attachment" not in code


async def test_mocked_bot_preserves_execute_errors() -> None:
    bot = MockedBot()
    bot.set_result("execute", {
        "response": [False], "execute_errors": [{"error_code": 100, "error_msg": "Invalid"}],
    })
    result = (await bot.execute_batch_detailed([("messages.delete", {"cmids": 7})]))[0]
    assert result.error is not None
    assert result.error.code == 100


def test_batch_builder_rejects_more_than_25_calls() -> None:
    with pytest.raises(ValueError, match="25"):
        build_execute_batch([VKCall("users.get", {})] * 26)
