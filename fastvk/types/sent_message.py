from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..exceptions import VKAPIError


@dataclass(frozen=True, slots=True)
class SentMessage:
    peer_id: int
    conversation_message_id: int
    message_id: int | None = None

    @classmethod
    def from_response(cls, response: Any, peer_id: int) -> SentMessage:
        if not isinstance(response, list) or len(response) != 1 or not isinstance(response[0], dict):
            raise RuntimeError("VK did not return a single-recipient message result")
        item = response[0]
        if item.get("peer_id", peer_id) != peer_id:
            raise RuntimeError("VK returned a result for a different recipient")
        if isinstance(item.get("error"), dict):
            raise VKAPIError(item["error"])
        cmid = item.get("conversation_message_id")
        if type(cmid) is not int or cmid <= 0:
            raise RuntimeError("VK did not return a valid conversation_message_id")
        message_id = item.get("message_id")
        return cls(peer_id, cmid, message_id if type(message_id) is int else None)
