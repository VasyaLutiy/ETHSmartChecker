# Задача для Морфа, фаза 6, задача 2 из 2: компоненты `ingest` и `cli`

> Дата: 29.09.2026. Проект ETHSmartChecker. Запись системы — `contour.yaml`, группы
> `ingest` (Functions `Ingest Block`, `Follow Chain`) и `cli` (Function `Command Line`);
> контракт этой задачи внесён коммитом `b27fea9`: параметр `on_alerts` на обоих уровнях,
> ключ `day` в `summary`, день ledger на каждый блок, флаш строк `ALERT` по завершении
> блока, `KeyboardInterrupt` в любой точке `listen`/`backfill`. Источники — `docs/TASK_PHASE6.md`
> §7 (долги, оставленные задачей 1) и `docs/TASK_PHASE5.md` §13 (факт живого смоука, долг
> Контура 3). Где Контур не уточняет форму вывода, уточняет §2.2 этого файла. Фикстуры —
> `tests/fixtures/`, новых нет. **Сеть не нужна и запрещена** в тестах и приёмках.
> Разбивки на карты здесь нет — она в `morph-map.json`.

## 1. Зачем это

Алерт — это и есть продукт пруфа: проверка 4 из `plan.md` §7 («`seed add` → `ALERT` на
копию») прошла именно им, 127 алертов за ~30 минут с двух сидов. Задача 1 фазы 6 сделала
Ctrl-C чистым выходом, и тем самым **узаконила потерю алертов**, которую сама же вынесла в
§7 как долг. Три дефекта, все три с числами.

- **Алерты блоков, завершённых в прерванном проходе, теряются навсегда.** `follow_chain`
  отдаёт `alerts` только через `return` (`ethsc/ingest.py:224,229`), а `cli` на
  `KeyboardInterrupt` выбрасывает весь `summary` (`ethsc/cli.py:95–96`). В смоуке проход
  шёл секунды–минуты при паузе 12 с, то есть Ctrl-C почти всегда приходится на проход; из
  двух проверочных прерываний оба пришлись на него. Потеря не восстанавливается перезапуском:
  адреса записаны, прогресс сдвинут, и на возобновлении они пропускаются как известные
  (`ethsc/ingest.py:93–95`), а `match_watchlist` вызывается только для впервые записанного
  адреса (`ethsc/ingest.py:116–119`). При темпе смоука 127 алертов за 30 минут одно
  прерывание стоит алертов всех блоков прохода — молча, без следа в логе.
- **Алерты незавершённого блока теряются даже без Ctrl-C.** `summary["alerts"]` пополняется
  только для `complete`-блока (`ethsc/ingest.py:221–224`); блок, обрезанный бюджетом или
  `max_calls_per_block`, уносит свои алерты с собой, хотя адреса уже записаны. В смоуке два
  из трёх запусков `listen` закончились именно остановкой по бюджету
  (`--daily-budget 1000000`, затем 2 000 000; ledger 1 999 800 за 28.09), то есть это не
  редкий путь, а штатный конец суток.
- **Расход пишется в день начала прохода, а не блока.** `day` вычисляется один раз на вызов
  `follow_chain` (`ethsc/ingest.py:161–164`) — долг Контура 3 из §13 фазы 5. `listen`
  обновляет день на каждом проходе (`ethsc/cli.py:83`), поэтому ошибается ровно один проход
  в сутки — тот, что пересёк полночь UTC, — но ошибается на весь свой расход: по фикстурным
  ценам это 17 560 кредитов одного блока, при живом темпе смоука ≈ 7 тыс. на блок. Следствие
  хуже самой суммы: новые сутки начинаются с ledger, куда уже записан чужой расход, и
  `--daily-budget` останавливает приём раньше, чем исчерпана суточная квота Infura (3 млн).

Плюс хвост задачи 1: `KeyboardInterrupt` перехвачен только вокруг `follow_chain`
(`ethsc/cli.py:84–96`) и вокруг `sleep` (`ethsc/cli.py:140–143`). Печать алертов
(`ethsc/cli.py:100`), запись строки остановки (`ethsc/cli.py:104–111`), промежуток между
проходом и паузой и `store.close()` (`ethsc/cli.py:274–275`) не покрыты — Ctrl-C там даёт
трейсбек и выход по сигналу, ровно тот дефект, который задача 1 закрывала.

**База: 180 тестов зелёные**, `venv/bin/python -m pytest tests -q --tb=line`, 73 с, 29.09,
дерево на `b27fea9`. Ни один существующий тест новому контракту **не противоречит**: три
примера `Follow Chain` передают `day="2026-09-28"` явно и остаются зелёными, потому что
явная строка по-прежнему прибивает весь проход; тесты на `ALERT` и на строку остановки
проверяют формат, а не момент печати, а порядок строк не меняется.

## 2. Контракт

### 2.1. Формы ВХОДНЫХ данных (что придётся конструировать, и где это определено)

- **Алерт** — `dict` ровно с ключами `address`, `seed_address`, `label`, `score`; строится в
  `ethsc/ingest.py:120–128` из результата `match_watchlist(store, code, min_score=0.8)`
  (`ethsc/cluster.py:139`, возвращает `seed_address`, `label`, `score`). Именно такой dict
  уходит в `on_alerts`.
- **`stats`** — результат `ingest_block`, ровно ключи `candidates`, `known`, `fetched`,
  `contracts`, `eoas`, `failed`, `deferred`, `complete`, `alerts` (`ethsc/ingest.py:79–89`).
  Инварианты: `candidates = known + fetched + deferred`, `fetched = contracts + eoas + failed`.
- **`summary`** — результат `follow_chain`, теперь ровно ключи `blocks`, `stopped`,
  `progress`, `alerts`, **`day`** (`ethsc/ingest.py:172–177` — добавляется пятый).
  `stopped` ∈ {`None`, `"budget"`, `"cap"`}; `progress` — `store.get_progress()`, `None` на
  свежей базе.
- **API `Store`**: `has_address` (`ethsc/store.py:102`), `get_progress` (`:169`),
  `set_progress` (`:178`), `spend(day, method, credits)` (`:220`), `spent(day) -> int`
  (`:228`). Схема базы не меняется.
- **`PRICES`** — `ethsc/config.py:6`: `eth_blockNumber` 80, `eth_getBlockReceipts` 1000,
  `eth_getCode` 80.
- **Источники `KeyboardInterrupt`**: `rpc.call` (транспорт и backoff-сон `RpcClient`,
  `ethsc/rpc.py:68`), `get_code` внутри `ingest_block` — его `except Exception`
  (`ethsc/ingest.py:102`) `KeyboardInterrupt` **не** ловит, это `BaseException`, и так и
  должно остаться; запись в `Store`; `sleep(interval)`; запись в `sys.stdout`/`sys.stderr`.
- **День как callable**: `day` принимает строку `"%Y-%m-%d"`, функцию без аргументов,
  возвращающую такую строку, или `None`. Для тестов и проб брать ровно такое выражение,
  отдельного стаба не заводить:
  ```python
  days = iter(["2026-09-28", "2026-09-28", "2026-09-29"])
  summary = follow_chain(rpc, store, day=lambda: next(days), prices=PRICES, ...)
  ```
  Порядок разрешения дня: один раз перед списанием `eth_blockNumber`, затем заново перед
  каждым блоком; проход из двух блоков дергает callable трижды.
- **Стабы тестов, две разные истории — читать внимательно:**
  - `tests/test_cli.py` и `tests/test_cli_examples.py` уже живут на `tests/helpers.py`
    (`FakeRpc`, `temp_store`, `block_codes`, `block_receipts`, `load_hex`), 0 своих классов.
    Для них правило прежнее: импортировать стабы оттуда, своих не писать.
  - `tests/test_ingest.py` и `tests/test_ingest_examples.py` написаны **до** появления
    `tests/helpers.py` и держат собственные `_codes()`, `_receipts()`, `_fresh_store()` и
    свой `class FakeRpc` (`tests/test_ingest_examples.py:50`). **Мигрировать их запрещено**:
    у локального `FakeRpc` порядок аргументов `(receipts, codes, head_hex)`, у хелперного —
    обратный, `FakeRpc(codes=None, receipts=None, head=…, fail=…)`
    (`tests/helpers.py:105`), и механическая замена даёт красное на ровном месте. Новые
    тесты в этих двух файлах используют **тот же локальный** `FakeRpc`; из `tests.helpers`
    берётся только `load_hex`. Второго фейка в файле появиться не должно.
- **`tests/helpers.py` получает один новый стаб** — обёртку, поднимающую
  `KeyboardInterrupt` на N-м вызове любого rpc, потому что ни один из существующих фейков
  не умеет прерваться на конкретном вызове:
  ```python
  class InterruptAfter(object):
      """Wraps an rpc: answers the first n calls, raises KeyboardInterrupt after."""
      def __init__(self, inner, n): ...
      def call(self, method, params): ...
  ```
  Имя, докстрока и поведение — обязательны; `calls` внутреннего фейка остаётся доступен
  через `.inner`. Больше в `tests/helpers.py` ничего не меняется, существующие
  `FakeRpc`/`FakeTransport`/загрузчики — байт в байт.
- **Фикстуры** (`tests/fixtures/`, не меняются): `receipts_26077729.json` (218 расписок,
  206 кандидатов), `codes_26077729.json` (206 ключей, 59 из них `"0x"`), `code_belle.hex`,
  `code_belle_copy_1807090d.hex`. Пара BELLE даёт `score` ровно **0.8667** на адресе
  `0x1807090dd15a6f58e00fd769e32ebf20ee610385`.

### 2.2. Формы ВЫХОДНЫХ данных

**Сток алертов `on_alerts`.** Один необязательный параметр, одно имя, два уровня:

- `ingest_block(..., on_alerts=None)` — если задан, вызывается **ровно один раз за вызов**,
  единственным позиционным аргументом: список алертов этого блока, отсортированный по
  `address`. Вызывается на **обоих** выходах: и когда функция возвращает `stats`, и когда
  `get_code` поднял `KeyboardInterrupt` — тогда со списком, набранным до прерывания, и
  **до того**, как исключение уйдёт наверх. Список может быть пустым; вызов всё равно
  происходит. Возвращаемый `stats["alerts"]` остаётся прежним.
- `follow_chain(..., on_alerts=None)` — передаётся в каждый вызов `ingest_block` как есть.
  Сам `follow_chain` его не вызывает и не оборачивает: у стока ровно один вызов на блок.
- **Каждый алерт попадает в сток ровно один раз.** Поэтому тот, кто печатает из
  `on_alerts`, не печатает `summary["alerts"]` повторно.

**`summary` из `follow_chain`** — пять ключей:

| ключ | было | стало |
|---|---|---|
| `blocks` | число полных блоков | без изменений |
| `stopped` | `None`/`budget`/`cap` | без изменений |
| `progress` | `store.get_progress()` | без изменений |
| `alerts` | конкатенация только полных блоков | конкатенация **всех** блоков прохода, включая незавершённый |
| `day` | — | строка последнего разрешённого дня |

**День ledger.** `day=None` — дата UTC, разрешаемая заново перед каждым блоком и один раз
перед списанием `eth_blockNumber`. `day="2026-09-28"` — прибивает весь проход (так живут
три существующих примера). `day=<callable>` — вызывается в тех же точках. Все списания
блока идут на день этого блока, включая проверку `spent(day) + price <= daily_budget` и
вычисление `allowed` для `max_calls`.

**stdout `cli`.** Строки `ALERT` пишутся и **флашатся** по завершении блока, из `on_alerts`,
а не копятся до конца прохода. Формат строки не меняется:
`"ALERT\t<address>\t<seed_address>\t<label>\t%.4f\n"`. Порядок строк тот же, что и сегодня:
блоки по возрастанию, внутри блока адреса по возрастанию — поэтому ни один существующий
ожидаемый вывод не меняется. `summary["alerts"]` в `cli` больше не печатается.

**Строка остановки (код 3)** — формат прежний,
`stopped: <stopped>, spent <N> credits, progress <P>\n`, с двумя уточнениями:

- `<N>` — `store.spent(summary["day"])`, то есть ledger **того дня, на который проход
  списывал последним**, а не дня старта; `cli` больше не вычисляет день сам и передаёт
  `day=None`;
- `<P>` — `summary["progress"]` десятичным числом или слово `none`, если он `None` (в коде
  это уже так, `ethsc/cli.py:109`; здесь это закрепляется контрактом).

**Чистая остановка по Ctrl-C.** `KeyboardInterrupt` где угодно внутри `listen` или
`backfill` даёт: код возврата 0; ни одной строки `Traceback` ни в stdout, ни в stderr; своей
строки про Ctrl-C нет; прогресс — последний полный блок; `store.close()` выполнен. «Где
угодно» теперь включает: `sleep`, `rpc.call`, backoff-сон, `ingest_block`, запись в `Store`,
**печать строк `ALERT`**, **запись строки остановки**, промежуток между проходом и паузой.
Алерты блоков, завершённых в прерванном проходе, и алерты прерванного блока к этому моменту
**уже напечатаны** — в этом вся задача.

Всё остальное — без изменений: код 0 при `stopped is None`, код 1 при `RpcError` (stderr —
`str(err)`), код 2 при ошибке использования, форматы всех подкоманд, схема базы, `RpcClient`.

### 2.3. Имена

- `on_alerts` — имя параметра в `ingest_block` и в `follow_chain`, последним в сигнатуре,
  по умолчанию `None`.
- `summary["day"]` — имя нового ключа.
- `day` — имя параметра, тип расширяется до `str | callable | None`.
- `InterruptAfter` — имя нового стаба в `tests/helpers.py`, поля `inner`, `n`.
- Значения `stopped` (`budget`, `cap`), литералы `stopped: `, `, spent `,
  ` credits, progress `, `none`, префикс `ALERT` — не переименовывать.
- `ethsc.cli.main(argv=None, rpc=None, sleep=None) -> int` — сигнатура не меняется.
- Внутренние хелперы `ethsc/cli.py` (`_follow`, `_print_alerts`, `_run_listen`,
  `_run_backfill`) можно менять и удалять; `_utc_day` (`ethsc/cli.py:56`) удаляется —
  день теперь приходит из `summary`.

### 2.4. Что не должно сломаться

- Все 180 существующих тестов, без правки ни одного. Отдельно назову те, что ближе всего к
  огню:
  - `tests/test_ingest_examples.py` — три примера `Follow Chain` с явным
    `day="2026-09-28"`/`"2026-09-29"` (17 560; 111 вызовов и 9960; 95 вызовов);
  - `tests/test_ingest.py::…::test_follow_chain` — 17 560 с явным `day`;
  - `tests/test_cli.py` — строка `ALERT` на копию BELLE со `score` 0.8667;
  - `tests/test_cli_examples.py` — `stopped: budget, spent 0 credits, progress none` и
    `spent 9960`, а также два теста Ctrl-C из задачи 1.
- Инварианты `stats` и порядок алертов по адресу.
- `ingest_block` по-прежнему **возвращает** `alerts`; сток их не заменяет.
- `except Exception` в `ethsc/ingest.py:102` остаётся: он не должен начать ловить
  `KeyboardInterrupt`.
- `RpcClient.on_spend` остаётся неподключённым; единственный писатель ledger — `follow_chain`.

## 3. Приёмка

База: **180 тестов**. `pytest` идёт через обёртку фаз 4–6, подменяющую
`socket.getaddrinfo` / `socket.socket.connect` / `socket.create_connection` на
`OSError("network blocked")`, с `INFURA_API_KEY=TESTKEY-ENV-0000` в окружении. Везде
`-q --tb=line`. «Проба оркестратора» — скрипт в самой приёмке, печатающий
`<сценарий>: got …, want …` по каждому расхождению и кончающийся ненулевым кодом; он, а не
тесты исполнителя, судит полноту.

### 3.1. Область «код `ingest`» (`ethsc/ingest.py`, `tests/test_ingest.py`, `tests/helpers.py`)

1. `ast.parse(..., feature_version=(3,9))` по всем трём файлам.
2. Стражи **по `ast`, не по тексту**:
   - `ethsc/ingest.py` не импортирует `urllib`, `http`, `socket`, `sqlite3`;
   - в `ethsc/ingest.py` нет `ExceptHandler` без типа; обработчик вокруг `get_code`
     остаётся с типом `Exception` (`KeyboardInterrupt` обязан проходить сквозь него), а
     любой **другой** обработчик в файле, если исполнитель его завёл, обязан кончаться
     голым `raise` — `ast.Raise` с `exc is None` в теле; проверяется обходом
     `ast`, не грепом;
   - `tests/helpers.py` не импортирует `urllib`, `http`, `socket`, и в нём есть `ClassDef`
     с именем `InterruptAfter`;
   - `tests/test_ingest.py` — не больше 7 функций `test_*`, ровно ноль `ClassDef` с именем,
     начинающимся на `Fake`.
3. **Проба оркестратора** (сеть заблокирована), сценарии с точными числами:
   - `ingest_block` на фикстуре блока 26077729 без `on_alerts` → `candidates` 206,
     `fetched` 206, `contracts` 147, `eoas` 59, `failed` 0, `complete` True, в базе 130 кодов
     (регрессия, пример 1 Контура);
   - `ingest_block` с `on_alerts`, база с сидом `code_belle.hex` («BELLE honeypot»),
     кандидаты `0x1807090dd15a6f58e00fd769e32ebf20ee610385` (отдаётся
     `code_belle_copy_1807090d.hex`) и `0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc`,
     `get_code` поднимает `KeyboardInterrupt` на втором адресе → `KeyboardInterrupt`
     доходит до пробы, и **до этого** сток позван ровно один раз со списком из одного
     алерта: `address` `0x1807090d…`, `score` 0.8667;
   - `ingest_block` с `on_alerts` на блоке без единого алерта → сток позван ровно один раз,
     со списком нулевой длины;
   - `follow_chain`, head `0x18dea22`, одни и те же расписки на оба блока, прогресс
     26077728, `day=lambda: next(iter(["2026-09-28","2026-09-28","2026-09-29"]))` (итератор
     создать один раз, не в лямбде), `daily_budget` 3 000 000 → `blocks` 2, `progress`
     26077730, `spent("2026-09-28")` 17 560, `spent("2026-09-29")` 1000,
     `summary["day"] == "2026-09-29"`;
   - тот же проход с `day="2026-09-28"` строкой → `spent("2026-09-28")` 18 560,
     `spent("2026-09-29")` 0, `summary["day"] == "2026-09-28"` (явный день прибивает проход);
   - `follow_chain` с `max_calls_per_block=1` на блоке BELLE + `0xb4e1…` → `stopped` `"cap"`,
     прогресс не сдвинут, сток позван ровно один раз со списком из одного алерта, и
     `len(summary["alerts"]) == 1`;
   - `follow_chain` с `on_alerts`, где `eth_getCode` поднимает `KeyboardInterrupt` на первом
     же вызове первого блока → исключение доходит до пробы, сток позван ровно один раз;
   - регрессия трёх примеров Контура: 17 560; `stopped "budget"` после 111 `eth_getCode` и
     9960; 95 вызовов на новом дне и `progress` 26077729.
4. `pytest tests/test_ingest.py -q --tb=line`.
5. `pytest tests -q --tb=line` — полный прогон, все зелёные.
6. Страж Secret Hygiene: настоящий ключ из `.env` не встречается ни в `ethsc/*.py`,
   `tests/*.py`, ни в выводе приёмки; вывод печатается с заменой ключа на `<KEY>`.

### 3.2. Область «судья `ingest`» (`tests/test_ingest_examples.py`, код не трогает)

1. `ast.parse`; стражи по `ast`: в файле ровно **один** `ClassDef` с именем на `Fake`
   (существующий локальный `FakeRpc`, миграция запрещена), файл импортирует `load_hex` из
   `tests.helpers`, не импортирует `urllib`/`http`/`socket`, функций `test_*` не меньше 12
   (9 было + 3 новых примера Контура).
2. `pytest tests/test_ingest_examples.py -q --tb=line`.
3. **Мутационная проверка**: копия дерева во временный каталог, где `ethsc/ingest.py`
   заменён на версию `4532c94` (до правок фазы 6 задачи 2) — прогон
   `tests/test_ingest_examples.py` на ней падает **не меньше чем 3 тестами** (сток при
   прерывании, сток на незавершённом блоке, день на каждый блок); считаются `failed` плюс
   сорвавшийся `KeyboardInterrupt`.
4. `pytest tests -q --tb=line` — все зелёные.
5. Страж Secret Hygiene, как в 3.1.

### 3.3. Область «код `cli`» (`ethsc/cli.py`, `tests/test_cli.py`)

1. `ast.parse` по обоим файлам.
2. Стражи по `ast`:
   - `ethsc/cli.py` не импортирует `urllib`, `http`, `socket`, `sqlite3`;
   - ни одного `ExceptHandler` без типа и ни одного, называющего `BaseException`;
   - **в `ethsc/cli.py` нет имени `_utc_day`** и ни один вызов `follow_chain` не имеет
     ключевого аргумента `day` — день приходит из `summary` (структурная проверка того,
     что офлайн иначе не проверить);
   - `tests/test_cli.py` — не больше 8 функций `test_*`, импортирует из `tests.helpers`,
     ноль `ClassDef` с именем на `Fake`.
3. **Проба оркестратора** (сеть заблокирована, `TESTKEY-0000` в окружении, stdout и stderr
   каждого вызова `main` перехвачены, `sleep` — записывающий фейк):
   - база с сидом BELLE, прогресс 26077728, head `0x18dea22`, единственный кандидат блока
     26077729 — копия BELLE, rpc обёрнут `InterruptAfter(inner, 3)` (прерывание на
     `eth_getBlockReceipts` блока 26077730) → `main(["--db", db, "listen"], rpc=…,
     sleep=…)` даёт код 0, stdout — **ровно одна** строка `ALERT` с `0x1807090d…`,
     `BELLE honeypot`, `0.8667`, stderr пуст, без `Traceback`, прогресс 26077729, `sleep` не
     вызван;
   - то же через `backfill --from 26077729 --to 26077730` → код 0, та же одна строка `ALERT`;
   - `backfill` на блоке BELLE + `0xb4e1…` с `--max-calls-per-block 1` → код 3, stdout — одна
     строка `ALERT`, stderr — ровно одна строка `stopped: cap, …` (алерт незавершённого
     блока напечатан **до** строки остановки);
   - Ctrl-C **во время печати алертов**: `sys.stdout`, чей `write` поднимает
     `KeyboardInterrupt` на первом вызове → код 0, без `Traceback` в stderr;
   - Ctrl-C **во время записи строки остановки**: `sys.stderr`, чей `write` поднимает
     `KeyboardInterrupt` → код 0, без `Traceback`;
   - четыре строки таблицы строк остановки из `docs/TASK_PHASE6.md` §2.2 — код и stderr
     точно, stdout пуст: `progress none` при пустом прогрессе; `spent 9960 credits,
     progress 26077728`; `stopped: cap, spent 1480 credits, progress none`; `listen` с
     `--daily-budget 10000` → код 3 и `sleep` не вызван;
   - регрессия задачи 1: `listen` с `FakeRpc(codes=<dict, поднимающий KeyboardInterrupt>)` →
     код 0, stdout и stderr пусты, прогресс 26077728, `sleep` не вызван; `listen` с
     `sleep`, поднимающим `KeyboardInterrupt` → код 0, `sleep == [12]`, прогресс 26077729;
     `listen` с `FakeRpc(fail=RpcError(None, "transport failed"))` → код 1, stderr одна
     строка, без `Traceback` и без `TESTKEY-0000`.
4. `pytest tests/test_cli.py -q --tb=line`.
5. `pytest tests -q --tb=line` — все зелёные.
6. Страж Secret Hygiene, как в 3.1.

### 3.4. Область «судья `cli`» (`tests/test_cli_examples.py`, код не трогает)

1. `ast.parse`; стражи по `ast`: импорт стабов из `tests.helpers`, ноль `ClassDef` с именем
   на `Fake`, функций `test_*` не меньше 12 (10 было + 2 новых примера Контура).
2. `pytest tests/test_cli_examples.py -q --tb=line`.
3. **Мутационная проверка**: копия дерева, где `ethsc/cli.py` **и** `ethsc/ingest.py`
   заменены на версии `4532c94` — прогон `tests/test_cli_examples.py` падает не меньше чем
   2 тестами (алерт пережил прерывание; алерт незавершённого блока). Оба файла обязательны:
   новый `cli.py` без нового `ingest.py` не импортируется.
4. `pytest tests -q --tb=line` — все зелёные.
5. Страж Secret Hygiene, как в 3.1.

### 3.5. Проза, после рана

Число тестов ≥ 190; `git diff 4532c94 -- ethsc/` трогает ровно `ethsc/ingest.py` и
`ethsc/cli.py` и ничего больше; `git diff 4532c94 -- tests/helpers.py` добавляет только
`InterruptAfter`.

## 4. Ограничения

- Python 3.12 в рантайме, синтаксис совместим с 3.9, только стандартная библиотека.
- Конверты правок: `ethsc/ingest.py` ~30–50 строк, `ethsc/cli.py` ~25–45,
  `tests/helpers.py` ~15 (один класс, чисто аддитивно). Не влезает — резать карту, а не
  расширять срез.
- Один файл — один владелец в поколении. `tests/helpers.py` пишется вместе с
  `ethsc/ingest.py` (первое поколение), чтобы `InterruptAfter` существовал до карт `cli`.
- Карты `cli` читают новую сигнатуру `follow_chain`, поэтому идут после `ingest`.
- **Не трогаются**: `ethsc/rpc.py`, `ethsc/store.py`, `ethsc/config.py`, `ethsc/cluster.py`,
  `ethsc/evm.py`, `ethsc/fingerprint.py`, `ethsc/__main__.py`, фикстуры, `contour.yaml`
  (уже поправлен, `b27fea9`), `morph-map.json`.
- Миграция `tests/test_ingest*.py` на `tests.helpers.FakeRpc` **запрещена** (см. §2.1:
  обратный порядок аргументов).
- `KeyboardInterrupt` ловится по имени; голый `except:` и `except BaseException` запрещены —
  они проглотили бы `SystemExit`.
- Собственные тесты кодовых карт — смоук, не полнота: сравнивают скаляры и короткие
  значения, не целые списки; `maxDiff` не нужен. Полноту судит проба из §3 и карты судей.
- No Network In Core, Secret Hygiene, Deterministic Output, Budget Respected — как в фазах 4–6.
- Правка файла во время рана даёт соседям `stale-context`; дерево во время рана не трогается.

## 5–6. Техники; что не указано

Как в `TASK_TEMPLATE`. Не указано: как именно `ingest_block` гарантирует вызов стока на обоих
выходах (`try/finally`, `else`+`except BaseException`+`raise` — на усмотрение, лишь бы
`KeyboardInterrupt` уходил наверх неизменным); где в `ethsc/cli.py` стоит внешний перехват
(`main`, диспетчер или обёртка) — лишь бы покрывал печать, строку остановки и промежуток до
паузы, а `store.close()` всё равно выполнялся; как печатается и флашится строка `ALERT`;
имена новых тестов.

## 7. Вне области

- **Окно между `put_address` и `match_watchlist`** (`ethsc/ingest.py:114–119`): если
  Ctrl-C приходит ровно туда, адрес записан, алерт не посчитан, и на возобновлении адрес
  известен — алерт потерян. Окно в несколько байткодов без единого I/O; закрывать его значит
  тащить транзакцию внутрь `ingest_block`. Названо вслух и оставлено.
- Восстановление алертов, потерянных прошлыми запусками: пересчёта `match_watchlist` по уже
  известным адресам нет и не будет в этой задаче.
- Отличимость прерванного `backfill` от завершённого по коду выхода (оба 0 по Контуру).
- Строка в stderr при Ctrl-C; обработка SIGTERM; демон, systemd, автоперезапуск.
- Реальный сигнал SIGINT в подпроцессе: в приёмке не проверяется (в подпроцесс не
  инъецировать `rpc`) — это живой смоук Джона.
- Скорость `similar` (MinHash/LSH), долг Контура 4 из §13 фазы 5.
- Любые правки `store.py`, `rpc.py`, `config.py`, `cluster.py`, фикстур, `contour.yaml`.

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
| карт в колоде | 4 (`ingest`, `ingest-judge`, `cli`, `cli-judge`) |
| поколений | 3 (`ingest` → {`ingest-judge`, `cli`} → `cli-judge`) |
| счёт исполнителя | $0.05–0.20 |
| карт с регенерацией | 1–2 |
| тестов после | 190–200 |

**Опровергаемое утверждение:** ни одна карта не сгорит окончательно, но хотя бы одна
потребует регенерации, и это будет `ingest` — на гарантии вызова стока при
`KeyboardInterrupt` (соблазн написать `except Exception` вместо `finally`) либо на том, что
явная строка `day` перестанет прибивать проход и три старых примера покраснеют.

## 10. Что записать в конце

Принято/сожжено карт, регенерации (что было в красном), минуты на поколение, счёт
провайдера, итоговое число тестов, имя ветки `morph/<run-id>`, строка разведки (сколько
файлов назвал скаут / сколько тронула колода / что добавлено руками и почему, минуты и
`stop_reason` скаута, его счёт отдельно).
