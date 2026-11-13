from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from fastvk import Uploader
from fastvk.api.client import Bot


class BoundedStream(BytesIO):
    def read(self, size: int = -1) -> bytes:
        assert 0 < size <= 64 * 1024
        return super().read(size)


@pytest.mark.parametrize("source", ["path", "string", "stream"])
@pytest.mark.parametrize("status", [200, 500])
async def test_upload_streams_and_respects_file_ownership(
    source: str, status: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"media" * 100_000
    stream = BoundedStream(b"skip" + content)
    stream.seek(4)
    path = tmp_path / "photo.jpg"
    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: stream)

    async def upload(request: web.Request) -> web.Response:
        assert request.content_length is not None
        reader = await request.multipart()
        part = await reader.next()
        assert part is not None
        assert part.name == "photo"
        assert part.filename == "custom.jpg"
        received = bytearray()
        while chunk := await part.read_chunk():
            received.extend(chunk)
        assert received == content
        return web.json_response({"photo": "uploaded"}, status=status)

    app = web.Application()
    app.router.add_post("/", upload)
    bot = Bot(token="test-token")
    file = stream if source == "stream" else str(path) if source == "string" else path
    try:
        async with TestServer(app) as server:
            operation = Uploader(bot)._upload_file(str(server.make_url("/")), file, "custom.jpg", "photo")
            if status == 200:
                assert await operation == {"photo": "uploaded"}
            else:
                with pytest.raises(RuntimeError, match="500"):
                    await operation
        assert stream.closed is (source != "stream")
    finally:
        stream.close()
        await bot.close()


@pytest.mark.parametrize("failure", [False, True])
async def test_download_to_streams_and_preserves_destination_on_failure(
    failure: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "file.bin"
    destination.write_bytes(b"original")
    content = b"chunk" * 20_000

    async def chunks(_size: int):
        yield content
        if failure:
            raise OSError("connection lost")
        yield content

    response = MagicMock()
    response.content.iter_chunked = chunks
    response.read = AsyncMock(side_effect=AssertionError("buffered download"))
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    bot = Bot(token="test-token")
    monkeypatch.setattr(bot, "_get_session", AsyncMock(return_value=session))
    if failure:
        with pytest.raises(OSError, match="connection lost"):
            await bot.download_to("https://example.test/file", destination)
        assert destination.read_bytes() == b"original"
    else:
        assert await bot.download_to("https://example.test/file", destination) == destination
        assert destination.read_bytes() == content * 2
    assert sorted(tmp_path.iterdir()) == [destination]


async def test_cancelled_download_removes_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()

    async def chunks(_size: int):
        yield b"partial"
        started.set()
        await asyncio.Event().wait()

    response = MagicMock()
    response.content.iter_chunked = chunks
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    bot = Bot(token="test-token")
    monkeypatch.setattr(bot, "_get_session", AsyncMock(return_value=session))
    task = asyncio.create_task(bot.download_to("https://example.test/file", tmp_path / "file.bin"))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert list(tmp_path.iterdir()) == []
