# Задача для Морфа, фаза 4: компоненты `rpc` и `ingest`

> Дата: 28.09.2026. Проект ETHSmartChecker, план — `plan.md` §5, фаза 4 («Сеть и приём»).
> Запись системы — `contour.yaml`, компоненты `rpc` (Function `RPC Client`, Data Object
> `RPC Response`) и `ingest` (Function `Discover Candidates`, `Ingest Block`, `Follow Chain`).
> Контур в этой фазе не меняется; уточнения, которых в нём нет, заданы здесь (§2.2) и
> записаны в §11 как долг Контура. Фикстуры — `tests/fixtures/`, опись —
> `tests/fixtures/README.md`. Новых фикстур нет. **Сеть не нужна и запрещена**: все тесты и
> приёмки офлайн, на записанных ответах через инъецируемый транспорт, `rpc` и `get_code`.
> Разбивки на карты здесь нет.

## 1. Зачем это

После фазы 3 база умеет хранить, кластеризовать и искать похожий код, но код в неё
кладёт только тест руками:

- блок 26077729 (`receipts_26077729.json`: 218 квитанций, 626 логов) даёт 206
  адресов-кандидатов (135 разных `to`, 119 разных адресов логов, 1 `contractAddress`);
  из них 147 с кодом, 59 без кода, 130 разных `code_id`. Функции, которая из квитанций
  получает эти 206 адресов и складывает их в `Store`, нет;
- один блок стоит 1000 кредитов `eth_getBlockReceipts` + 206 × 80 `eth_getCode` = 17 480,
  с `eth_blockNumber` — 17 560. При бюджете 10 000 кредитов в сутки блок обрывается на
  111-м `eth_getCode`; без учёта кредитов до вызова и без возобновления незавершённого
  блока (resume) такой обрыв либо превышает бюджет, либо теряет 95 адресов;
- в рабочей сети Infura отвечает 429 на всплеск (`rpc_429.json`, 25 параллельных
  запросов) и объектом ошибки на будущий блок; клиента с повтором, бюджетом и без утечки
  ключа в текст ошибки нет;
- `match_watchlist` фазы 3 никем не вызывается: копия BELLE (13/15 = 0.8667) в новом
  блоке сейчас не поднимет алерт. Фаза 5 (`cli listen/backfill`, строки `ALERT`,
  exit 3 на бюджетной остановке) строится на `follow_chain`.

## 2. Контракт

### 2.1. Формы ВХОДНЫХ данных

| форма | где определена | как построить в тесте |
|---|---|---|
| квитанции блока | `tests/fixtures/receipts_26077729.json`: `{"jsonrpc","id","result": [218 dict]}`; ключи квитанции: `to`, `from`, `contractAddress`, `logs` (список `dict` с `address`), и др.; `to`/`contractAddress` бывают `null`; адреса в смешанном регистре | `json.load(open(p))["result"]`; синтетика — `[{"to": "0x…", "contractAddress": None, "logs": []}]` |
| код кандидата | `tests/fixtures/codes_26077729.json`: `{address: "0x…"}`, 206 ключей, строчные, отсортированы; 59 значений `"0x"`; ключи — ровно ожидаемые кандидаты блока | фейковый `get_code(address, block)` → `codes[address]` |
| `code_*.hex` | `tests/fixtures/README.md`, текст результата `eth_getCode` | `open(p).read().strip()` — строка; байты — `bytes.fromhex(text[2:])` |
| ответ 429 | `tests/fixtures/rpc_429.json`: `{"status": 429, "headers", "body": "<JSON-текст>", "captured"}` | фейковый транспорт → `(d["status"], d["body"].encode())` |
| транспорт | Контур, `RPC Client`: `transport(url, body: bytes) -> (status: int, body: bytes)` | функция/объект, пишет вызовы в список, отдаёт заготовленные ответы |
| `rpc` для `follow_chain` | этот §2.2: объект с методом `call(method, params) -> result` | класс-фейк: `eth_blockNumber` → `"0x18dea21"`, `eth_getBlockReceipts` → список квитанций, `eth_getCode` → `codes[address]`; пишет `(method, params)` в список |
| `Store` | `ethsc/store.py:49`; `put_code` :63, `put_address` :88, `has_address` :102, `code_of` :110, `fingerprints` :131, `get_progress` :169, `set_progress` :178, `add_seed` :188, `seeds` :208, `spend` :220, `spent` :228, `close` :57 | `Store(os.path.join(tempfile.mkdtemp(), "t.db"))` |
| `match_watchlist` | `ethsc/cluster.py:139`: `(store, code: bytes, min_score=0.8)` → список Alert `{seed_address, label, score}` | вызывается, не строится; сид — `put_code` + `put_address` + `add_seed` |
| адреса BELLE | `tests/fixtures/README.md` | сид `0x34c6211621f2763c60eb007dc2ae91090a2d22f6` (`code_belle.hex`), копия `0x1807090dd15a6f58e00fd769e32ebf20ee610385` (`code_belle_copy_1807090d.hex`) |

### 2.2. Формы ВЫХОДНЫХ данных

Где этот раздел точнее `contour.yaml` (ключ `alerts` в сводке `follow_chain`, ключ
`address` в алерте `ingest_block`, `"cap"`, `watch`, `env_path`, запись расхода), верен
этот раздел.

**`ethsc/config.py`** — только данные, без импортов:
`PRICES = {"eth_blockNumber": 80, "eth_getBlockReceipts": 1000, "eth_getCode": 80}`; на
строке ключа `eth_blockNumber` — комментарий `# не подтверждено, сверить с дашбордом`.

**`ethsc/rpc.py`** — единственный сетевой модуль:

- `class RpcError(Exception)`: `RpcError(code, message)`, атрибуты `.code`, `.message`;
  `str(e)` содержит `message`. `code` — код JSON-RPC ошибки (`-32001`), HTTP-статус
  после исчерпания повторов (`429`, `503`), `None` для сбоя транспорта или разбора.
- `RpcClient(url, transport=None, sleep=time.sleep, prices=None, on_spend=None, max_retries=3)`;
  `transport=None` → POST через `urllib.request` (JSON, `Content-Type: application/json`,
  таймаут), `HTTPError` превращается в `(status, body)`; конструктор в сеть не ходит.
  `prices=None` → `ethsc.config.PRICES`.
- `.call(method, params) -> result`: тело запроса — JSON
  `{"jsonrpc": "2.0", "id": <int>, "method": method, "params": params}`, транспорт
  вызывается с `url` клиента. Статус 200 и `"result"` в ответе → вернуть `result`
  как есть. Статус 429 или 5xx, а также `OSError` из транспорта → повтор после
  `sleep(1)`, `sleep(2)`, `sleep(4)` … (удвоение от 1), не больше `max_retries` повторов,
  всего `max_retries + 1` вызовов транспорта; затем `RpcError`. Объект `"error"` в
  ответе 200 → `RpcError(error["code"], error["message"])` сразу, без повтора и без `sleep`.
  Любой другой статус, тело не JSON, нет ни `result`, ни `error` → `RpcError` сразу.
- `on_spend(method, prices.get(method, 0))` вызывается ровно один раз после каждого
  успешного `call` и ни разу после неуспешного; `on_spend=None` — не вызывается.
- **Secret Hygiene:** ни `str(e)`, ни `repr(e)`, ни `e.args`, ни полный текст трейсбэка
  `traceback.format_exception(type(e), e, e.__traceback__)` не содержат URL и ключ.
  Текст исключения транспорта в `RpcError` не переносится (он содержит URL); цепочка
  исключений подавлена (`raise … from None`). Клиент ничего не печатает и не логирует.
- `infura_url(env_path=".env") -> str`: `"https://mainnet.infura.io/v3/" + key`, где
  `key` — `os.environ["INFURA_API_KEY"]`, иначе строка `INFURA_API_KEY=<key>` файла
  `env_path` (пробелы по краям и одна пара кавычек `"…"`/`'…'` вокруг значения
  снимаются, строки `#…` пропускаются). Нет ни там, ни там (или файла нет) →
  `RpcError(None, "INFURA_API_KEY is not set")`. Переменная окружения важнее файла.

**`ethsc/ingest.py`** — без сети, `rpc`, `get_code` и `store` инъецируются:

- `discover_candidates(receipts) -> list[str]`: отсортированный список разных строчных
  адресов — каждый `contractAddress`, каждый `to`, каждый `logs[].address`. `None`,
  отсутствующий ключ, отсутствующие `logs` пропускаются; `from` кандидатом не бывает;
  элемент, не являющийся `dict`, пропускается. `[]` → `[]`.
- `ingest_block(block, receipts, get_code, store, max_calls=None, watch=None) -> dict`
  ровно с ключами `candidates, known, fetched, contracts, eoas, failed, deferred,
  complete, alerts`:
  - кандидаты обходятся в порядке `discover_candidates`; `store.has_address(a)` → `known`;
  - каждый другой — один вызов `get_code(a, block)` (адрес строчный, `block` — `int`),
    пока число вызовов меньше `max_calls` (`None` — без предела); остальные — `deferred`;
  - `fetched` — число вызовов `get_code`, включая упавшие;
  - `"0x"` → `put_address(a, None, block)`, `eoas`; иная `0x`-hex строка →
    `put_address(a, put_code(bytes), block)`, `contracts`; `get_code` бросил исключение,
    вернул не строку или строку, которая не `0x` + чётное число hex-цифр → `failed`,
    адрес не сохраняется, блок продолжается;
  - `complete` = `deferred == 0` (упавшие адреса не держат блок: пропуск по Tolerant Parser);
  - `alerts`: для каждого адреса, сохранённого в этом вызове с кодом, —
    `match_watchlist(store, code)` (при `watch` не `None` — `min_score=watch`), каждый
    Alert дополнен ключом `address`: `dict` ровно с ключами `address, seed_address,
    label, score`; список упорядочен по `address`, внутри — в порядке `match_watchlist`.
    Алерты возвращаются, не печатаются;
  - инварианты: `candidates == known + fetched + deferred`,
    `fetched == contracts + eoas + failed`.
- `follow_chain(rpc, store, start=None, stop=None, max_calls_per_block=None,
  daily_budget=None, day=None, prices=None) -> dict` ровно с ключами
  `blocks, stopped, progress, alerts`:
  - один вызов `rpc.call("eth_blockNumber", [])` → `head = int(result, 16)`; затем блоки
    от `start` (если задан), иначе `get_progress() + 1`, иначе `head`, до
    `min(stop, head)` (или `head`) включительно; на каждый блок
    `rpc.call("eth_getBlockReceipts", [hex(block)])` и `ingest_block` с
    `get_code = rpc.call("eth_getCode", [address, hex(block)])`;
  - цена метода — `prices.get(method, 0)` (`prices=None` → `{}`); `day=None` → текущая
    дата UTC `"YYYY-MM-DD"`; после каждого успешного вызова `rpc` —
    `store.spend(day, method, price)`; `follow_chain` — единственный, кто пишет расход в
    `Store` (фейк `rpc` сам ничего не учитывает);
  - **Budget Respected:** перед каждым вызовом `spent(day) + price <= daily_budget`
    (`None` — без предела); иначе вызова нет, остановка `stopped = "budget"`.
    `eth_getCode` внутри блока не делается сверх остатка бюджета: например,
    `max_calls = min(max_calls_per_block, (daily_budget − spent(day)) // price)`;
  - `set_progress(block)` — только после `complete` блока; незавершённый блок →
    остановка: `"budget"`, если его оборвал бюджет, иначе `"cap"` (оборвал
    `max_calls_per_block`); повторный вызов начинает тот же блок заново, известные
    адреса пропускаются;
  - `stopped` — `None`, если пройдены все блоки до конца диапазона; `"budget"`/`"cap"` —
    как выше. `blocks` — число завершённых в этом вызове блоков; `progress` —
    `get_progress()` в конце; `alerts` — алерты всех `ingest_block` этого вызова по
    порядку блоков;
  - исключение из `eth_blockNumber`/`eth_getBlockReceipts` пробрасывается как есть,
    `progress` не меняется; исключение `eth_getCode` — это `failed` одного адреса.

### 2.3. Имена

- `ethsc/config.py`: `PRICES`. `ethsc/rpc.py`: `RpcError`, `RpcClient`, `RpcClient.call`,
  `infura_url`. `ethsc/ingest.py`: `discover_candidates`, `ingest_block`, `follow_chain`.
- Ключи статистики и сводки — §2.2, строки `"budget"`, `"cap"`.
- Тесты: `tests/test_rpc.py`, `tests/test_ingest.py` (кодовые карты),
  `tests/test_rpc_examples.py`, `tests/test_ingest_examples.py` (судьи).
- Фиктивный ключ в тестах — `TESTKEY-0000` (или `TESTKEY-…`); настоящий ключ из `.env`
  не читается ни одним тестом: тест `infura_url` задаёт окружение (`mock.patch.dict`) или
  `env_path` во временном каталоге.
- Числа из `examples` `contour.yaml` проверены оркестратором по фикстурам 28.09:
  206 = ключи `codes_26077729.json`; 135/119/1; 147/59/130; 50·4 + 6; 17 560;
  80 + 1000 + 111·80 = 9960 ≤ 10 000 < 10 040; 206 − 111 = 95.

### 2.4. Что не должно сломаться

`ethsc/evm.py`, `ethsc/fingerprint.py`, `ethsc/store.py`, `ethsc/cluster.py`,
`ethsc/__init__.py` и все 11 тестовых файлов фаз 1–3 — байт в байт; 123 теста зелёные.
`contour.yaml`, `plan.md`, `tests/fixtures/*`, `.env` не трогаются. `ingest` не
импортирует ни `ethsc.rpc`, ни `ethsc.config` (цены и `rpc` приходят параметрами).

## 3. Приёмка

Базовая линия: 123 теста (`123 passed`). Все `pytest` в приёмках идут через обёртку,
которая до запуска подменяет `socket.getaddrinfo` и `socket.socket.connect` на
`OSError("network blocked")`, с `INFURA_API_KEY=TESTKEY-ENV-0000` в окружении.

1. **Кодовая карта `rpc`** (`ethsc/rpc.py`, `ethsc/config.py`, `tests/test_rpc.py`):
   1. `ast.parse(..., feature_version=(3,9))` по трём файлам;
   2. стражи по `ast` (узлы `Import`/`ImportFrom`, не текст): `ethsc/config.py` без
      импортов; `ethsc/rpc.py` импортирует только stdlib и `ethsc.config`, в нём есть
      импорт `urllib`; ни один другой `ethsc/*.py` не импортирует `urllib`, `http`,
      `socket`; `tests/test_rpc.py` не импортирует `urllib`, `http`, `socket`;
   3. **проба оркестратора** (сеть заблокирована): `PRICES` точно; комментарий
      `не подтверждено, сверить с дашбордом` через `tokenize` стоит на строке
      `eth_blockNumber`; пять examples `RPC Client` точными значениями (результат,
      число вызовов транспорта, список `sleep`, `code`, сумма 1160) плюс: тело запроса
      (`jsonrpc`, `method`, `params`), `url` у транспорта, 503 как 429, `max_retries=0`
      → 1 вызов, 404 и не-JSON → `RpcError` сразу, `on_spend` молчит на ошибке,
      `prices=None` → `on_spend("eth_blockNumber", 80)`; для `TESTKEY-0000` — ни в
      `str`, `repr`, `args`, ни в `format_exception`; `infura_url` из окружения, из
      временного `.env` (с кавычками и без), приоритет окружения, `RpcError` без обоих.
      Печатает `<Function> <N>: got …, want …` по каждому расхождению;
   4. `pytest tests/test_rpc.py -q --tb=short` через обёртку;
   5. `pytest tests -q --tb=short` через обёртку;
   6. страж Secret Hygiene: настоящий ключ (читается приёмкой из `.env`, если он есть) не
      встречается ни в `ethsc/*.py`, `tests/*.py`, ни в выводе приёмки; вывод печатается
      с заменой ключа на `<KEY>`.
2. **Кодовая карта `ingest`** (`ethsc/ingest.py`, `tests/test_ingest.py`):
   1. `ast.parse` по обоим файлам;
   2. стражи по `ast`: `ethsc/ingest.py` не импортирует `urllib`, `http`, `socket`,
      `sqlite3`, `ethsc.rpc`, `ethsc.config` и не обращается к атрибуту `_conn`; No
      Network In Core по всем `ethsc/*.py`, кроме `rpc.py`; тест не импортирует сеть;
   3. **проба оркестратора** (сеть заблокирована, `stdout` перехвачен и должен быть
      пуст): Discover Candidates 1–2 (206 = ключи `codes_26077729.json`, наличие
      `0xb53c071b…`, ни одного чистого `from`, смешанный регистр, `None`, пропуски
      ключей); Ingest Block 1–4 точными `dict` статистики плюс 130 отпечатков, порядок
      и аргументы вызовов `get_code`, `deferred` 156/106/56/6/0, битый hex и не-строка →
      `failed`; алерт на копию BELLE точным `dict` (`score == 13/15` по `similarity`),
      `watch=0.9` → `[]`, WETH9 → `[]`; Follow Chain 1–3 (сводка, `spent`, число и
      аргументы вызовов `eth_getCode`, прогресс) плюс бюджет < 80 → ни одного вызова,
      бюджет 1000 → только `eth_blockNumber`, `max_calls_per_block=50` → `"cap"`, пустая
      база без `start` → блок головы, `start`/`stop`, два блока подряд (голова
      `0x18dea22` с пустыми квитанциями) → `blocks 2`, прогресс на голове → 0 блоков и
      один вызов, исключение `eth_getBlockReceipts` пробрасывается. Печатает
      `<Function> <N>: got …, want …`;
   4. `pytest tests/test_ingest.py -q --tb=short` через обёртку;
   5. `pytest tests -q --tb=short` через обёртку.
3. **Карты судей** (`tests/test_rpc_examples.py`, `tests/test_ingest_examples.py`, по
   тесту на example, код не трогают): `ast.parse`, свой файл
   `pytest … -q --tb=short`, затем `pytest tests -q --tb=short`, оба через обёртку;
   судья `rpc` — плюс страж Secret Hygiene из 1.6.
4. Итог фазы: полный `pytest -q --tb=short` зелёный, в нём 123 теста фаз 1–3 и не
   меньше 14 тестов судей (5 + 2 + 4 + 3).

Каждая приёмка обёрнута в снимок `/tmp/morph/<card>/` с логом `acc-<время>-<pid>.log`
и возвращает код своей цепочки. Эталонной реализации нет: приёмки прогнаны вручную и
красные на отсутствующем модуле, на пустом модуле (`ImportError` в пробе), на
заглушках, возвращающих `None`/`{}`/`[]`, и на мутациях стражей: импорт `urllib` в
`ingest.py`, обращение к `store._conn`, тест, печатающий `.env` (ключ заменён на `<KEY>`,
приёмка красная), тест с импортом `socket`, тест, обходящий страж импорта и зовущий
`urlopen` (`OSError: network blocked`).

Тесты пишутся на `unittest`, у каждого assert есть `msg=`; в классах, сравнивающих списки
и словари, — `maxDiff = None`. Базы и `.env` — только во временных каталогах. Хелперы
тестов не называются `test_*` (фаза 2, §11). Настоящий `.env` тесты не читают.

## 4. Ограничения

- Python 3.12 в рантайме, синтаксис совместим с 3.9, только стандартная библиотека.
- Все цели — новые файлы: `ethsc/config.py`, `ethsc/rpc.py`, `ethsc/ingest.py` и их тесты.
  Существующие файлы не правятся — рамка правки не применяется.
- Один файл — одна карта-владелец. Судья пишет только свой тест.
- No Network In Core: `urllib`, `http`, `socket` импортирует только `ethsc/rpc.py`.
- Secret Hygiene: ключ — только из окружения или `.env`; ни в тексте ошибок, ни в выводе,
  ни в тестах, ни в колоде.
- Budget Respected: проверка до вызова; цены — из `ethsc/config.py` (для `rpc`) или из
  параметра `prices` (для `follow_chain`), не литералами в логике.
- `ingest` и `rpc` не читают друг друга физически (контракт `rpc` у `follow_chain` —
  утиный `call`), поэтому идут одним поколением.
- Во время рана дерево не трогается: правка файла из среза даёт `stale-context`.

## 5–6. Техники; что не указано

Как в TASK_TEMPLATE. Не указаны: `id` запроса JSON-RPC (любое `int`), таймаут
`urllib`, заголовки кроме `Content-Type`, внутренние хелперы, способ разбора `.env`
сверх §2.2, как именно `follow_chain` урезает `max_calls` по бюджету (если приёмка
зелёная).

## 7. Вне области

- компонент `cli` (`python -m ethsc`, `listen`/`backfill`, печать строк `ALERT`, exit 3,
  связка `RpcClient(infura_url())` → `follow_chain` с `config.PRICES`) — фаза 5;
- бесконечный цикл опроса головы и пауза между опросами: `follow_chain` делает один
  проход до головы;
- batch-запросы JSON-RPC, WebSocket, `trace_*`, `eth_getLogs`, подписки;
- заголовок `Retry-After`, джиттер, лимит запросов в секунду;
- дневной бюджет и потолок по блокам по умолчанию в `config.py` (кроме `PRICES`);
- расход на неуспешные вызовы (429, ошибки) — не учитывается;
- повтор упавших `eth_getCode` адресов в том же блоке; реорганизации цепи;
- правка `ethsc/evm.py`, `fingerprint.py`, `store.py`, `cluster.py`, `contour.yaml`,
  фикстур; новые фикстуры; любой запрос в настоящую сеть.

## 8. Как запускать

```bash
cd /home/john/Documents/Work2026/ETHSmartChecker
set -a; source /home/john/Documents/Work2026/MorphProject/morph-lab/.env; set +a
~/Documents/python_venv/venv_mrph/bin/mrph deck check --root .
~/Documents/python_venv/venv_mrph/bin/mrph run --root . --processor glm --max-regenerations 6 --pretty
```

Исполнитель — `glm` (route sync). Перед стартом дерево чистое.

## 9. Пререгистрация

| величина | прогноз |
|---|---|
| карт в колоде | 4 (`rpc`, `ingest` — обе `variants: 2`; `rpc-judge`, `ingest-judge`) |
| поколений | 2 (`rpc` ∥ `ingest` → оба судьи) |
| счёт исполнителя | $0.03–0.20 |
| карт с регенерацией | 1–3 |
| конфликтов `write-write` на preflight | 0 |
| тестов после | ≥ 123 + 14 (судьи) + собственные тесты карт |

**Опровергаемое утверждение:** обе кодовые карты проходят пробу оркестратора не
позже `r1`, и ни одна красная первая попытка не вызвана стражем, сработавшим на
текст (все стражи — по `ast`). Если `ingest` сгорит на `follow_chain`, разночтение
сидит в месте, которое Контур не называет (кто пишет расход, урезание `max_calls`
бюджетом, `"cap"`), и его надо внести в Контур.

## 10. Что записать в конце

Принято/сожжено карт, регенерации (что было в красном), минуты на поколение, счёт
провайдера, итоговое число тестов, доллары на принятую карту, имя ветки
`morph/<run-id>`, строка разведки (скаут не запускался — все цели новые), статус
сбоев Морфа (а) срез судьи из мапы, (б) checkout после рана.

## 11. Факт

_Заполняется после рана._
