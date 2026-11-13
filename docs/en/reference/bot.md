# Bot

`Bot` is the core class. `FastVK` extends it with `run_polling()`.

## Constructor

```python
Bot(
    token: str,
    group_id: int,
    *,
    storage: BaseStorage | None = None,
    lifespan: AsyncContextManager | None = None,
    api_version: str = "5.199",
)
```

| Parameter | Type | Description |
|---|---|---|
| `token` | `str` | VK community token |
| `group_id` | `int` | VK community ID |
| `storage` | `BaseStorage` | FSM storage. Default: `MemoryStorage()` |
| `lifespan` | async context manager | Startup/shutdown hook |
| `api_version` | `str` | VK API version. Default: `"5.199"` |
| `timeout` | `float` | Per-request HTTP timeout in seconds. Default: `30.0` |
| `max_retries` | `int` | Retries for network errors and codes 1/6/9/10/29. Default: `3` |
| `captcha_handler` | `async (sid, img_url) -> answer` | Solver invoked on error code 14 |
| `max_concurrency` | `int` | `FastVK` only — cap on updates processed in parallel (`0` = unbounded) |
| `polling` | `"group"` \| `"user"` | `FastVK` only — long-poll flavour. Default: `"group"` |

## Methods

### start_polling

```python
async def start_polling(self, *, skip_updates: bool = False) -> None
```

Start long-polling loop. Blocks until `stop()` is called or process interrupted.

- `skip_updates=True` — discard queued updates before starting.

### stop

```python
async def stop(self) -> None
```

Gracefully stop the polling loop.

### get_me

```python
async def get_me(self) -> Group
```

Return info about the bot's community (calls `groups.getById`).

### collect

```python
async def collect(
    method_class: type[VKMethod],
    *,
    max_total: int = 0,
    items_key: str | None = None,
    count: int = 100,
    offset: int = 0,
    **kwargs,
) -> list[Any]
```

Automatically iterate over all pages of a paginated VK API method.

Accepts a typed method class — full IDE autocomplete.

```python
from fastvk.methods import GroupsGetMembers, WallGet, MessagesGetHistory

# All group members (auto-paginated)
members = await bot.collect(GroupsGetMembers, group_id=123, fields="photo_200")

# Recent posts (max 500)
posts = await bot.collect(WallGet, owner_id=-123, count=100, max_total=500)

# Chat history
history = await bot.collect(MessagesGetHistory, peer_id=2000000001)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `method_class` | — | Typed VK method class (e.g. `GroupsGetMembers`) |
| `max_total` | `0` | Limit total items (`0` = unlimited) |
| `items_key` | auto | Response key with item list (auto-detected) |
| `count` | `100` | Items per page |
| `offset` | `0` | Starting offset |

### get_user

```python
async def get_user(self, user_id: int, fields: str = "") -> User
```

Return user info (calls `users.get`).

```python
user = await bot.get_user(123456)
user = await bot.get_user(123456, fields="photo_200,city")
```

### Message formatting

`messages.send` and `messages.edit` accept `parse_mode=ParseMode.MARKDOWN`
or `"markdown"`. FastVK converts `__bold__` and `_italic_` to VK `format_data`
and removes the markers from the message. Offsets use UTF-16 and the visible
text of `@id123(Name)` / `@club123(Name)` mentions. Unclosed markers remain literal.
This is a limited syntax, not a full Markdown or HTML parser.

Formatting works for dynamic calls, typed methods, `emit()`, `Message.answer()`,
`reply()`, `edit()`, and `CallbackQuery.edit_message()`. Without `parse_mode`,
text is unchanged. JSON `content_source` metadata is preserved; the legacy
`content_source="markdown"` spelling is accepted for compatibility.

The pure functions `get_format_data_for_message()` and
`prepare_formatted_message_params()` are available from `fastvk.formatting`.
Preparation does not mutate the input and can be repeated safely.

### send_message / edit_message / delete_message

```python
sent = await bot.send_message(123, "Hello", random_id=12345)
await bot.send_message(123, "Reply", reply_to_conversation_message_id=sent.conversation_message_id)
await bot.edit_message(123, sent.conversation_message_id, "Updated")
await bot.delete_message(123, sent.conversation_message_id, delete_for_all=1)
```

`send_message()` sends to one `peer_id` using VK's `peer_ids` response form.
It returns an immutable `SentMessage` with `peer_id`, `conversation_message_id`,
and optional `message_id`. A missing local ID raises `RuntimeError`; a recipient
API error raises `VKAPIError`. Global IDs are never substituted for local IDs.
Text is optional for media-only messages. Extra API parameters, including
`parse_mode`, `keyboard`, `attachment`, and `disable_mentions`, are forwarded.
The generated `random_id` is reused across retries; pass your own stable value
when retries must also survive restarts.

The helpers use `conversation_message_id` in their signatures. VK receives
`cmid` for edits, `cmids` for deletes, and `forward.conversation_message_ids`
for replies. Generic `VKCall.send_message`, `VKCall.edit_message`, and
`VKCall.delete_message` factories build the same requests for `.emit(bot)`
or `execute_batch_detailed()`. To receive a local ID from a send factory, use
`extended_result=True`, then `SentMessage.from_response(result.value, peer_id)`.
No mention suppression, formatting, or delete-for-everyone policy is implicit.
Existing `bot.messages.send(peer_id=...)` still returns a global ID.

### execute / execute_batch

```python
async def execute(self, code: str) -> Any
async def execute_batch(self, calls: list[tuple[str, dict]]) -> list[Any]
```

`execute()` runs a VKScript snippet server-side. `execute_batch()` packs up to
25 API calls into one request and returns their results in order.

```python
results = await bot.execute_batch([
    ("users.get", {"user_ids": 1}),
    ("groups.getById", {"group_id": 1}),
])
```

### execute_detailed / execute_batch_detailed

`execute_detailed(code, **params)` returns the complete VK response envelope,
including `execute_errors`. Ordinary `execute()` still returns only `response`.
`execute_batch_detailed(calls)` accepts `(method, params)` tuples or `VKCall`
objects and splits them into sequential batches of at most 25 calls.

```python
from fastvk import VKCall

results = await bot.execute_batch_detailed([
    VKCall("messages.edit", {"peer_id": 123, "cmid": 7, "message": "Updated"}),
    ("users.get", {"user_ids": 123}),
])
for result in results:
    if result.error is not None:
        print(result.error.code, result.error.message, result.error.method)
```

Each `VKCallResult` has `value`, optional `error`, and `succeeded`. Errors are
associated with failed (`false`) entries in order. Missing results are failures.
Nested errors do not trigger retries of successful operations in the same batch.
Top-level API and network errors use the client's existing retry policy.
Batch values are passed via `Args`; `parse_mode` works as in direct message calls.

### download

```python
async def download(self, url: str, dest: str | Path | None = None) -> bytes
```

Download a file (e.g. an attachment URL). Writes to `dest` if given.
The return value buffers the entire file in memory, even with `dest`.

### download_to

```python
async def download_to(self, url: str, dest: str | Path) -> Path
```

Stream a file to disk in 64 KiB chunks without buffering the entire response.
The destination is replaced only after a successful download. On error or
cancellation, the temporary file is removed and an existing destination is
preserved. The destination's parent directory must exist.

### set_captcha_handler

```python
def set_captcha_handler(self, handler: Callable[[str, str], Awaitable[str]]) -> None
```

Register `(captcha_sid, captcha_img_url) -> answer`. When VK returns error
code 14 the failed call is retried once with the answer.

### _call

```python
async def _call(self, method: str, **params) -> Any
```

Low-level API call. Retries network errors and codes 1/6/9/10/29 with
exponential backoff; raises `VKAPIError` otherwise.

## API namespaces

```python
bot.messages   # MessagesNamespace
bot.users      # UsersNamespace
bot.groups     # GroupsNamespace
bot.wall       # WallNamespace
bot.photos     # PhotosNamespace
bot.docs       # DocsNamespace
```

Each namespace has typed methods that return parsed models. Example:

```python
msg_id = await bot.messages.send(peer_id=123, message="Hi", random_id=0)
# msg_id: int

user_list = await bot.users.get(user_ids=123456)
# user_list: list[dict]
```
