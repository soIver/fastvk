# Bot

`Bot` — основной класс. `FastVK` расширяет его методом `run_polling()`.

## Конструктор

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

| Параметр | Тип | Описание |
|---|---|---|
| `token` | `str` | Токен VK сообщества |
| `group_id` | `int` | ID VK сообщества |
| `storage` | `BaseStorage` | FSM хранилище. По умолчанию: `MemoryStorage()` |
| `lifespan` | async context manager | Хук запуска/остановки |
| `api_version` | `str` | Версия VK API. По умолчанию: `"5.199"` |
| `timeout` | `float` | HTTP-таймаут запроса, сек. По умолчанию: `30.0` |
| `max_retries` | `int` | Повторы для сетевых ошибок и кодов 1/6/9/10/29. По умолчанию: `3` |
| `captcha_handler` | `async (sid, img_url) -> answer` | Решатель, вызываемый при коде ошибки 14 |
| `max_concurrency` | `int` | Только `FastVK` — лимит параллельно обрабатываемых апдейтов (`0` = без лимита) |
| `polling` | `"group"` \| `"user"` | Только `FastVK` — вид long poll. По умолчанию: `"group"` |

## Методы

### start_polling

```python
async def start_polling(self, *, skip_updates: bool = False) -> None
```

Запустить цикл long-polling. Блокирует до вызова `stop()` или прерывания процесса.

- `skip_updates=True` — выбросить накопившиеся апдейты перед стартом.

### stop

```python
async def stop(self) -> None
```

Мягко остановить цикл polling.

### get_me

```python
async def get_me(self) -> Group
```

Вернуть информацию о сообществе бота (вызывает `groups.getById`).

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

Автоматически проходит по всем страницам пагинированного VK API метода.

Принимает типизированный класс метода — полный автокомплит в IDE.

```python
from fastvk.methods import GroupsGetMembers, WallGet, MessagesGetHistory

# Все участники группы (авто-пагинация)
members = await bot.collect(GroupsGetMembers, group_id=123, fields="photo_200")

# Последние посты (максимум 500)
posts = await bot.collect(WallGet, owner_id=-123, count=100, max_total=500)

# История чата
history = await bot.collect(MessagesGetHistory, peer_id=2000000001)
```

| Параметр | По умолч. | Описание |
|----------|-----------|----------|
| `method_class` | — | Типизированный класс VK метода (например `GroupsGetMembers`) |
| `max_total` | `0` | Ограничить количество (`0` = без лимита) |
| `items_key` | авто | Ключ ответа со списком элементов (автоопределение) |
| `count` | `100` | Элементов на страницу |
| `offset` | `0` | Начальное смещение |

### get_user

```python
async def get_user(self, user_id: int, fields: str = "") -> User
```

Вернуть информацию о пользователе (вызывает `users.get`).

```python
user = await bot.get_user(123456)
user = await bot.get_user(123456, fields="photo_200,city")
```

### Форматирование сообщений

`messages.send` и `messages.edit` принимают `parse_mode=ParseMode.MARKDOWN`
или `"markdown"`. FastVK преобразует `__жирный__` и `_курсив_` в VK `format_data`
и удаляет маркеры из сообщения. Смещения рассчитываются в UTF-16 с учётом
видимого текста упоминаний `@id123(Имя)` / `@club123(Название)`. Незакрытые
маркеры остаются обычным текстом. Это ограниченный синтаксис, не полный Markdown или HTML.

Форматирование работает для динамических вызовов, типизированных методов,
`emit()`, `Message.answer()`, `reply()`, `edit()` и `CallbackQuery.edit_message()`.
Без `parse_mode` текст не меняется. JSON-метаданные `content_source` сохраняются;
старое написание `content_source="markdown"` поддерживается для совместимости.

Чистые функции `get_format_data_for_message()` и
`prepare_formatted_message_params()` доступны из `fastvk.formatting`.
Подготовка параметров не меняет исходный словарь и допускает повторный вызов.

### execute / execute_batch

```python
async def execute(self, code: str) -> Any
async def execute_batch(self, calls: list[tuple[str, dict]]) -> list[Any]
```

`execute()` выполняет сниппет VKScript на стороне сервера. `execute_batch()`
упаковывает до 25 вызовов API в один запрос и возвращает их результаты по порядку.

```python
results = await bot.execute_batch([
    ("users.get", {"user_ids": 1}),
    ("groups.getById", {"group_id": 1}),
])
```

### execute_detailed / execute_batch_detailed

`execute_detailed(code, **params)` возвращает полный ответ VK, включая
`execute_errors`. Обычный `execute()` по-прежнему возвращает только `response`.
`execute_batch_detailed(calls)` принимает пары `(method, params)` или объекты
`VKCall` и выполняет последовательные пакеты максимум по 25 вызовов.

```python
from fastvk import VKCall

results = await bot.execute_batch_detailed([
    VKCall("messages.edit", {"peer_id": 123, "cmid": 7, "message": "Обновлено"}),
    ("users.get", {"user_ids": 123}),
])
for result in results:
    if result.error is not None:
        print(result.error.code, result.error.message, result.error.method)
```

`VKCallResult` содержит `value`, необязательную `error` и признак `succeeded`.
Вложенные ошибки сопоставляются результатам `false` по порядку. Отсутствующие
результаты считаются неудачными. Вложенная ошибка не приводит к повтору успешных
операций того же пакета. Ошибки верхнего уровня и сети обрабатываются обычным
механизмом повторов клиента. Значения параметров передаются через `Args`;
`parse_mode` работает так же, как при непосредственном вызове метода.

### download

```python
async def download(self, url: str, dest: str | Path | None = None) -> bytes
```

Скачать файл (например, URL вложения). Пишет в `dest`, если задан.
Возвращаемое значение содержит весь файл в памяти, даже при указании `dest`.

### download_to

```python
async def download_to(self, url: str, dest: str | Path) -> Path
```

Скачать файл на диск порциями по 64 КиБ без накопления ответа целиком в памяти.
Целевой файл заменяется только после успешного скачивания. При ошибке или
отмене временный файл удаляется, а существующий целевой файл сохраняется.
Родительский каталог целевого файла должен существовать.

### set_captcha_handler

```python
def set_captcha_handler(self, handler: Callable[[str, str], Awaitable[str]]) -> None
```

Регистрирует `(captcha_sid, captcha_img_url) -> answer`. При коде ошибки 14 VK
неудавшийся вызов повторяется один раз с ответом.

### _call

```python
async def _call(self, method: str, **params) -> Any
```

Низкоуровневый API вызов. Повторяет сетевые ошибки и коды 1/6/9/10/29 с
экспоненциальной задержкой; иначе бросает `VKAPIError`.

## API пространства имён

```python
bot.messages   # MessagesNamespace
bot.users      # UsersNamespace
bot.groups     # GroupsNamespace
bot.wall       # WallNamespace
bot.photos     # PhotosNamespace
bot.docs       # DocsNamespace
```

Каждое пространство имён имеет типизированные методы, возвращающие разобранные модели. Пример:

```python
msg_id = await bot.messages.send(peer_id=123, message="Привет", random_id=0)
# msg_id: int

user_list = await bot.users.get(user_ids=123456)
# user_list: list[dict]
```
