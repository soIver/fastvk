from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .formatting import prepare_formatted_message_params

if TYPE_CHECKING:
    from .api.client import Bot

EXECUTE_BATCH_SIZE = 25
_METHOD = re.compile(r"[A-Za-z][A-Za-z0-9]*\.[A-Za-z][A-Za-z0-9]*\Z")
_PARAMETER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


@dataclass(frozen=True, slots=True)
class VKExecuteError:
    code: int
    message: str
    method: str | None = None
    request_params: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VKExecuteError:
        raw_params = data.get("request_params")
        return cls(
            code=int(data.get("error_code", 0)),
            message=str(data.get("error_msg", "Unknown error")),
            method=str(data["method"]) if data.get("method") is not None else None,
            request_params=tuple(item for item in raw_params if isinstance(item, dict))
            if isinstance(raw_params, list) else (),
        )


@dataclass(frozen=True, slots=True)
class VKCallResult:
    value: Any
    error: VKExecuteError | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.value is not False and self.value is not None


@dataclass(frozen=True, slots=True)
class VKCall:
    method: str
    params: dict[str, Any]

    def __post_init__(self) -> None:
        if not _METHOD.fullmatch(self.method):
            raise ValueError(f"Invalid VK API method: {self.method!r}")

    def prepared_params(self) -> dict[str, Any]:
        return prepare_formatted_message_params(self.method, self.params)

    async def emit(self, bot: Bot) -> Any:
        return await bot._call(self.method, **self.params)


def build_execute_batch(calls: list[VKCall]) -> tuple[str, dict[str, Any]]:
    if len(calls) > EXECUTE_BATCH_SIZE:
        raise ValueError("execute accepts at most 25 calls per request")
    arguments: dict[str, Any] = {}
    expressions: list[str] = []
    for index, call in enumerate(calls):
        params: list[str] = []
        for name, value in call.prepared_params().items():
            if value is None:
                continue
            if not _PARAMETER.fullmatch(name):
                raise ValueError(f"Invalid VK API parameter: {name!r}")
            argument = f"call_{index}_{name}"
            arguments[argument] = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
            params.append(f"{json.dumps(name)}:Args.{argument}")
        expressions.append(f"API.{call.method}({{{','.join(params)}}})")
    return f"return [{','.join(expressions)}];", arguments


def parse_execute_results(payload: dict[str, Any], count: int) -> list[VKCallResult]:
    values = payload.get("response")
    values = values if isinstance(values, list) else []
    raw_errors = payload.get("execute_errors")
    raw_errors = raw_errors if isinstance(raw_errors, list) else []
    results: list[VKCallResult] = []
    error_index = 0
    for value in values[:count]:
        error = None
        if value is False and error_index < len(raw_errors):
            raw_error = raw_errors[error_index]
            error_index += 1
            if isinstance(raw_error, dict):
                error = VKExecuteError.from_dict(raw_error)
        results.append(VKCallResult(value, error))
    results.extend(VKCallResult(False) for _ in range(count - len(results)))
    return results
