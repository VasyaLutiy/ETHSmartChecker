# Задача для Морфа, фаза 5: компонент `cli`

> Дата: 28.09.2026. Проект ETHSmartChecker, план — `plan.md` §5, фаза 5 («CLI и демо пруфа»).
> Запись системы — `contour.yaml`, компонент `cli` (Function `Command Line`). Контур в этой
> фазе не меняется; уточнения, которых в нём нет, заданы здесь (§2.2) и записаны в §12 как
> долг Контура. Фикстуры — `tests/fixtures/`, опись — `tests/fixtures/README.md`. Новых
> фикстур нет. **Сеть не нужна и запрещена** в тестах и приёмках: `rpc` инъецируется в
> `main()`, все ответы — из `tests/fixtures/` через `tests/helpers.FakeRpc`. Разбивки на
> карты здесь нет — она в `morph-map.json`.

## 1. Зачем это

После фазы 4 система умеет слушать блок, отбирать кандидатов, тянуть код, хранить,
кластеризовать, искать похожее и вести бюджет — но только из теста. Командной строки нет:
`ls ethsc/` даёт 8 файлов (`__init__.py`, `cluster.py`, `config.py`, `evm.py`,
`fingerprint.py`, `ingest.py`, `rpc.py`, `store.py`), ни одного `cli.py` или
`__main__.py`; `python -m ethsc` падает `No module named ethsc.__main__`. Без него:

- пруф фазы 5 (`plan.md` §7) требует ручного смоука — `listen` на ~300 блоков (~1 час),
  `clusters top`, `similar`, `seed add` + алерт на копию — ни одна из этих пяти операций
  сегодня не выполнима без интерпретатора и ручного кода;
- `match_watchlist`/`ingest_block` фазы 3–4 пишут алерты в `dict`, но их некому печатать
  строкой `ALERT`, которую видит человек;
- `follow_chain` (`ethsc/ingest.py:136`) делает один проход до головы и требует внешнего
  цикла с паузой между опросами — этого цикла нет нигде в дереве (в фазе 4 он явно вне
  области: «бесконечный цикл опроса головы и пауза между опросами» — `docs/TASK_PHASE4.md`
  §7); без него `listen` за час обработает только тот единственный блок, что был головой
  на момент старта (около 200 кандидатов), а не «≥ 1000 контрактов», как того требует
  критерий пруфа.

164 теста фаз 1–4 зелёные (`venv/bin/python -m pytest -q` — проверено 28.09, 38 с).

## 2. Контракт

### 2.1. Формы ВХОДНЫХ данных (что придётся конструировать, и где это определено)

| форма | где определена | как построить в тесте |
|---|---|---|
| `Store` | `ethsc/store.py:49`; `put_code` :63, `put_address` :88, `has_address` :102, `code_of` :110, `addresses_of` :121, `fingerprints` :131, `code_by_id` :158, `get_progress` :169, `set_progress` :178, `add_seed` :188 (raises `KeyError`), `seeds` :208, `spend` :220, `spent` :228, `close` :57 | `Store(path)`; `tests/helpers.temp_store()` для временной |
| `build_clusters`, `find_similar`, `match_watchlist` | `ethsc/cluster.py:22`, `:105`, `:139` — сигнатуры и формы `Cluster`/`Alert` в `contour.yaml` группа `cluster` | вызываются, не строятся |
| `follow_chain` | `ethsc/ingest.py:136`: `(rpc, store, start=None, stop=None, max_calls_per_block=None, daily_budget=None, day=None, prices=None) -> {blocks, stopped, progress, alerts}`; `stopped` — `None`/`"budget"`/`"cap"` | вызывается с `rpc` и `store`, инъецированными тестом |
| `rpc` для `follow_chain` | утиный `.call(method, params)`, как в фазе 4 | `tests/helpers.FakeRpc(codes=…, receipts=…, head=…, fail=…)` |
| `RpcClient`, `infura_url`, `RpcError` | `ethsc/rpc.py:49`, `:107`, `:16` | `RpcClient(infura_url())` — только когда CLI не получил `rpc` инъекцией (реальная сеть в тестах не вызывается — `rpc` всегда передан) |
| `PRICES` | `ethsc/config.py:6` — `{"eth_blockNumber": 80, "eth_getBlockReceipts": 1000, "eth_getCode": 80}` | `from ethsc.config import PRICES`, передаётся в `follow_chain(prices=PRICES)` |
| квитанции/код блока 26077729 | `tests/fixtures/receipts_26077729.json`, `codes_26077729.json` (206 кандидатов, 147 с кодом, 130 `code_id`, 59 EOA); `tests/fixtures/README.md` | `tests/helpers.block_receipts()`, `tests/helpers.block_codes()` |
| BELLE и её копия | `tests/fixtures/README.md`: сид `0x34c6211621f2763c60eb007dc2ae91090a2d22f6` (`code_belle.hex`), копия `0x1807090dd15a6f58e00fd769e32ebf20ee610385` (`code_belle_copy_1807090d.hex`), похожесть 13/15 = 0.8667 | `tests/helpers.load_hex(name)` |
| пара UniswapV2 для L0/similar | `0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc` и три адреса того же `code_id` (`0x22052a1a…`, `0x2621cc0b…`, `0x3041cbd3…`); четвёртый похожий `0xcf6daab95c476106eca715d48de4b13287ffdeaa` (26/32 = 0.8125) — посчитано в приёмке карты `cluster` фазы 3, воспроизведено здесь на том же наборе | `codes_26077729.json`, заполнить store в порядке `sorted(blk)` как в `tests/test_cluster.py` |
| 15 кластеров блока 26077729 | точный список (уровень, ключ, размер) — приёмка карты `cluster` фазы 3 (`docs/TASK_PHASE3.md`, `morph-map.json` карта `cluster`); 7 L0, 2 L1, 6 proxy | тот же store, тот же порядок вставки |

### 2.2. Формы ВЫХОДНЫХ данных (Контур не уточняет — уточняется здесь; в этих местах верен этот раздел, не `contour.yaml`)

**`ethsc/cli.py`** — единственный новый модуль с логикой; **`ethsc/__main__.py`** — тонкий
вызов (см. §4).

`main(argv=None, rpc=None, sleep=None) -> int`. `argv=None` → `sys.argv[1:]`. `rpc=None` →
`RpcClient(infura_url())` (сеть не заблокирована руками — конструктор `RpcClient` сам не
ходит в сеть; поход происходит только внутри `follow_chain`, если он реально вызван, то есть
только у `listen`/`backfill` без инъецированного `rpc`). `sleep=None` → `time.sleep`;
инъецируется для `listen`, чтобы опрос можно было остановить в тесте без реального ожидания.
`main` никогда не поднимает `SystemExit`: ошибку `argparse` (не хватает подкоманды,
неизвестный флаг) она ловит и возвращает её код как `int`, так что и `sys.exit(main())` в
`__main__.py`, и прямой вызов `main(...)` в тесте видят один и тот же `int`.

Общий флаг `--db PATH` (по умолчанию `ethsc.sqlite`), стоит до подкоманды.

Формат адреса всюду, где он принимается позиционным аргументом (`cluster`, `similar`,
`seed add`) — ровно `^0x[0-9a-fA-F]{40}$`; несовпадение → код 2, короткое сообщение в
`stderr`, ничего в `stdout`.

Подкоманды:

- **`backfill --from N --to M [--daily-budget C] [--max-calls-per-block K]`** — один вызов
  `follow_chain(rpc, store, start=N, stop=M, daily_budget=C, max_calls_per_block=K,
  prices=PRICES)`. После вызова печатает строки `ALERT` (см. ниже) из `summary["alerts"]`,
  в их порядке, и ничего больше. `summary["stopped"] is None` → код 0; `"budget"` или
  `"cap"` → код 3 (работа не закончена). Исключение `RpcError` из `follow_chain`
  (например, у `rpc.call` при первом же обращении) — код 1, в `stderr` ровно
  `str(err)` (гарантированно без ключа и URL — секретная гигиена `RpcError` уже это
  обеспечивает), в `stdout` ничего, без трейсбека.
- **`listen [--daily-budget C] [--max-calls-per-block K] [--interval S]`** — цикл: один
  вызов `follow_chain(rpc, store, daily_budget=C, max_calls_per_block=K, prices=PRICES)`
  (без `start`/`stop` — от `get_progress() + 1` или от головы, до головы на момент
  вызова); печатает алерты этого прохода; если `stopped` — `"budget"` или `"cap"` → код 3,
  цикл останавливается. Иначе — `sleep(interval)` (`interval` по умолчанию 12) и повтор.
  `KeyboardInterrupt`, пойманный вокруг `sleep`, — чистая остановка, код 0 (прогресс уже
  сохранён предыдущим полным проходом, работа не потеряна). `RpcError` — как у `backfill`,
  код 1.
- **`clusters top [--n K]`** (`K` по умолчанию 20) — первые `K` записей `build_clusters(store)`
  (порядок как в `ethsc/cluster.py:87`, порядок уже итоговый), по одной строке
  `<level>\t<key>\t<len(members)>`. Код 0, в том числе на пустой базе (0 строк).
- **`cluster <addr>`** — по одной строке на каждый `Cluster` из `build_clusters(store)`, где
  `addr.lower()` есть в `members` (обычно 0 или 1 строка): `<level>\t<key>\t<members
  через запятую>`. Код 0 всегда (в том числе 0 найденных).
- **`similar <addr> [--min 0.8]`** — `find_similar(store, addr, min_score)`, по одной
  строке `<address>\t<score:.4f>`, в порядке результата (score убывает, потом адрес). Код 0
  всегда.
- **`seed add <addr> --label L`** — `store.add_seed(addr, L)`. `KeyError` (адрес неизвестен
  или это EOA) → код 2, `stderr` без трейсбека. Иначе код 0, ничего в `stdout`.
- **`seed list`** — `store.seeds()`, по одной строке `<address>\t<label>` (порядок как у
  `seeds()` — по адресу). Код 0.

Строка алерта (в `backfill`/`listen`, из `summary["alerts"]`, где элемент —
`{address, seed_address, label, score}` фазы 4): ровно

```
ALERT\t<address>\t<seed_address>\t<label>\t<score:.4f>
```

Пример по фикстурам: `ALERT\t0x1807090dd15a6f58e00fd769e32ebf20ee610385\t0x34c6211621f2763c60eb007dc2ae91090a2d22f6\tBELLE honeypot\t0.8667`.

Все числа с плавающей точкой на выводе — `"%.4f"` (`1.0000`, `0.8125`, `0.8667`); во
внутренних структурах (`Alert`, `find_similar`) значение остаётся точным `float`
фазы 3–4, округление — только при печати.

`stdout` — только перечисленные выше записи, ничего больше (ни заголовков, ни отладочной
печати); `stderr` — только короткие однострочные сообщения об ошибке кодов 1 и 2.

### 2.3. Имена

- `ethsc/cli.py`: `main`. `ethsc/__main__.py`: не определяет новых имён, вызывает `main`.
- `tests/helpers.py`: `load_hex(name)`, `block_codes()`, `block_receipts()`, `temp_store()`,
  `FakeTransport`, `FakeRpc`.
- Тесты: `tests/test_cli.py` (кодовая карта, ≤ 5 тестов), `tests/test_cli_examples.py`
  (судья).
- Фиктивный ключ в тестах — `TESTKEY-0000` (как в фазах 3–4); настоящий ключ из `.env` не
  читается ни одним тестом.
- Коды выхода: `0` успех, `1` ошибка `RpcError` (сеть/бюджет ещё до первого прохода), `2`
  ошибка использования (`argparse`, неверный формат адреса, `seed add` на неизвестный
  адрес), `3` бюджетная/потолочная остановка (`stopped` не `None`) после хотя бы одного
  прохода `follow_chain`.

### 2.4. Что не должно сломаться

`ethsc/evm.py`, `fingerprint.py`, `store.py`, `cluster.py`, `rpc.py`, `config.py`,
`ingest.py`, `__init__.py` и все 13 тестовых файлов фаз 1–4 — байт в байт; 164 теста
зелёные. `contour.yaml`, `plan.md`, `tests/fixtures/*`, `.env` не трогаются. `ethsc/cli.py`
не импортирует `urllib`, `http`, `socket`, `sqlite3` напрямую (только `Store`).

## 3. Приёмка

Базовая линия: 164 теста (`164 passed`). Приёмки `pytest` идут через обёртку,
подменяющую `socket.getaddrinfo`/`socket.socket.connect`/`socket.create_connection` на
`OSError("network blocked")`, с `INFURA_API_KEY=TESTKEY-ENV-0000` в окружении (как в фазе
4).

1. **`test-helpers`** (`tests/helpers.py`):
   1. `ast.parse(..., feature_version=(3,9))`;
   2. страж по `ast`: `tests/helpers.py` не импортирует `urllib`, `http`, `socket`; не
      содержит функции `test_*` или класса `Test*` (не должен собираться `pytest`'ом как
      тестовый файл);
   3. **проба оркестратора** (сеть заблокирована): `block_codes()` — 206 ключей, 59
      значений `"0x"`; `block_receipts()` — список длины 218; `load_hex("code_weth9.hex")`
      — `bytes`, длина 3124; `temp_store()` — экземпляр `Store`, `get_progress() is None`,
      два вызова дают разные файлы; `FakeRpc().call("eth_blockNumber", [])` ==
      `"0x18dea21"`, `.call("eth_getBlockReceipts", ["0x18dea21"])` — список длины 218,
      `.call("eth_getCode", ["<адрес из block_codes()>"])` равен значению словаря;
      `FakeRpc(fail=RuntimeError("x")).call(...)` поднимает `RuntimeError`; `FakeTransport`
      отдаёт очередь ответов и пишет `(url, body)` в `.calls`;
   4. `pytest tests -q --tb=short` через обёртку (164 теста, `tests/helpers.py` не
      добавляет и не ломает ни одного).
2. **Кодовая карта `cli`** (`ethsc/cli.py`, `ethsc/__main__.py`,
   `tests/test_cli.py`):
   1. `ast.parse` по трём файлам;
   2. стражи по `ast`: `ethsc/cli.py` и `ethsc/__main__.py` не импортируют `urllib`,
      `http`, `socket`, `sqlite3`; ни один другой `ethsc/*.py`, кроме `ethsc/rpc.py`, их
      не импортирует; `ethsc/__main__.py` не содержит `FunctionDef`/`ClassDef`, не длиннее
      15 физических строк, и импортирует `ethsc.cli` (модуль или `main` из него);
      `tests/test_cli.py` не импортирует сеть, не больше 5 функций `test_*`, импортирует
      стабы из `tests.helpers` (проверка по `ast`: есть `ImportFrom` с `module ==
      "tests.helpers"` или `"helpers"`), не определяет собственный класс `FakeRpc` или
      `FakeTransport` (запрет по имени класса через `ast.ClassDef.name`);
   3. **проба оркестратора** (сеть заблокирована, `TESTKEY-0000` в окружении,
      `stdout`/`stderr` каждого вызова `main` перехвачены): подкоманда `--help` через
      `subprocess` (`venv/bin/python -m ethsc --help`, код 0, офлайн); прямые вызовы
      `main(argv, rpc=…)`:
      - `backfill --from 26077729 --to 26077729` с `FakeRpc(head="0x18dea21")` на свежей
        базе → код 0, `codes` 130 строк, `addresses` 206 строк (читает файл базы напрямую
        `sqlite3.connect(path).execute("SELECT COUNT(*) FROM …")`, не через `Store` —
        проверка приёмки, не пример для кода);
      - `--daily-budget 79` на той же паре подряд (свежая база, прогресс не задан) → код 3,
        `stdout` пуст (0 вызовов `eth_getCode`, бюджет обрывает на `eth_blockNumber`);
      - `clusters top` на store, заполненном из `codes_26077729.json` в порядке
        `sorted(blk)` (как приёмка карты `cluster` фазы 3) → ровно 15 строк, точный список
        `(level, key, size)` фазы 3;
      - `clusters top --n 3` на том же store → первые 3 строки того же списка;
      - `cluster 0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc` на том же store → ровно 1
        строка `L0\t8b5db55fa9ab3b9527508d4abe0b39eb588bf310270c8e04b3f38214e8ba63b4\t<4
        адреса через запятую по возрастанию>`;
      - `cluster 0x` + `"11"*20` (неизвестный адрес) → код 0, 0 строк;
      - `similar 0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc --min 0.8` на том же store →
        ровно 4 строки: три с `1.0000` в порядке адреса, затем
        `0xcf6daab95c476106eca715d48de4b13287ffdeaa\t0.8125`;
      - `seed add 0x34c6211621f2763c60eb007dc2ae91090a2d22f6 --label "BELLE honeypot"` на
        store с загруженным `code_belle.hex`, затем `seed list` → код 0 оба раза; вторая
        команда печатает ровно `0x34c6211621f2763c60eb007dc2ae91090a2d22f6\tBELLE
        honeypot`;
      - `seed add` на адрес без кода → код 2;
      - `similar not-an-address` → код 2;
      - без подкоманды (`["--db", path]`) → код 2 (без трейсбека);
      - `backfill` над блоком, чей единственный кандидат — `0x1807090dd15a6f58e00fd769e32ebf20ee610385`
        (фикстура `code_belle_copy_1807090d.hex`) на store, уже засеянном BELLE, → ровно
        одна строка `stdout`, начинается `ALERT`, равна точно
        `ALERT\t0x1807090dd15a6f58e00fd769e32ebf20ee610385\t0x34c6211621f2763c60eb007dc2ae91090a2d22f6\tBELLE honeypot\t0.8667`;
      - `listen` с `rpc=FakeRpc(fail=RpcError(None, "transport failed"))` → код 1,
        `TESTKEY-0000` не встречается ни в `stdout`, ни в `stderr`, ни одной строки
        `Traceback`;
      - `listen` с `rpc=FakeRpc(head="0x18dea21")` на store с прогрессом `26077728`, и
        `sleep`, поднимающим `KeyboardInterrupt` на первом вызове → код 0, `sleep` вызван
        ровно один раз с `12`, прогресс базы после вызова — `26077729`.
      Печатает `<сценарий>: got …, want …` по каждому расхождению;
   4. `pytest tests/test_cli.py -q --tb=short` через обёртку;
   5. `pytest tests -q --tb=short` через обёртку;
   6. страж Secret Hygiene: настоящий ключ (читается приёмкой из `.env`, если он есть) не
      встречается ни в `ethsc/*.py`, `tests/*.py`, ни в выводе приёмки; вывод печатается с
      заменой ключа на `<KEY>`.
3. **Карта судьи** (`tests/test_cli_examples.py`, по тесту на пример, код не трогает):
   `ast.parse`, страж импорта стабов из `tests.helpers` (как у карты 2), свой файл
   `pytest tests/test_cli_examples.py -q --tb=short`, затем `pytest tests -q --tb=short`,
   оба через обёртку, страж Secret Hygiene как в 2.6.
4. Итог фазы: полный `pytest -q --tb=short` зелёный, в нём 164 теста фаз 1–4 плюс собственные
   тесты `test-helpers`/`cli` (≤ 5) плюс не меньше 8 тестов судьи.

Каждая приёмка обёрнута в снимок `/tmp/morph/<card>/` с логом `acc-<время>-<pid>.log` и
возвращает код своей цепочки. Эталонной реализации нет: приёмки прогнаны вручную и красны
на отсутствующем модуле, на пустом модуле (`ImportError`/`NotImplementedError` в пробе), на
заглушках (`main` всегда возвращает 0 и ничего не печатает) и на мутациях стражей: импорт
`socket` в `cli.py`, обращение к `store._conn`, `tests/test_cli.py` с 8 тестами, тест,
печатающий `.env` (ключ заменён на `<KEY>`, приёмка красная).

Тесты пишутся на `unittest`, у каждого assert — `msg=`; в классах, сравнивающих списки и
словари, — `maxDiff = None`. Базы — только во временных каталогах (`tests.helpers.temp_store`
или `tempfile.mkdtemp()` вручную). Настоящий `.env` тесты не читают. Стабы — из
`tests/helpers.py`; свои копии `FakeRpc`/`FakeTransport`/загрузчиков фикстур в
`tests/test_cli.py` и `tests/test_cli_examples.py` не пишутся.

## 4. Ограничения

- Python 3.12 в рантайме, синтаксис совместим с 3.9, только стандартная библиотека.
- Все цели — новые файлы: `ethsc/cli.py`, `ethsc/__main__.py`, `tests/helpers.py`,
  `tests/test_cli.py`, `tests/test_cli_examples.py`. Существующие файлы не правятся.
- Один файл — одна карта-владелец: `tests/helpers.py` пишет только карта `test-helpers`;
  `ethsc/cli.py`, `ethsc/__main__.py`, `tests/test_cli.py` — только карта `cli`;
  `tests/test_cli_examples.py` — только карта-судья.
- No Network In Core: `urllib`, `http`, `socket` — только `ethsc/rpc.py`; `ethsc/cli.py`
  использует `RpcClient`/`infura_url` (импорт модуля, не сети) и получает готовый `rpc` в
  тестах.
- Secret Hygiene: ключ — только из окружения или `.env`; ни в тексте ошибок `cli`, ни в
  выводе, ни в тестах, ни в колоде.
- `ethsc/__main__.py` — тонкий вызов: импортирует `main` из `ethsc.cli` и передаёт ему
  управление под `if __name__ == "__main__":`; никакой логики разбора аргументов или работы
  со `Store` в нём.
- `cli` и `cli-judge` читают, что пишет `test-helpers` (`tests/helpers.py`)
  — это физическая зависимость по чтению, они идут позже него.
- Во время рана дерево не трогается: правка файла из среза даёт `stale-context`.

## 5–6. Техники; что не указано

Как в `TASK_TEMPLATE`. Не указаны: библиотека разбора аргументов (`argparse` — самый
естественный выбор для stdlib, но контур не называет её по имени); порядок флагов внутри
подкоманды; текст сообщений об ошибках в `stderr` (кроме требования — короткие, без
трейсбека, без ключа); внутренние хелперы `ethsc/cli.py`; ровно как форматируется адрес на
выводе (регистр — контур не требует ни исходного, ни lowercase; фикстуры дают lowercase
через `addresses_of`/`find_similar`, поэтому вывод будет lowercase естественным образом, но
это не отдельное требование).

## 7. Вне области

- живой смоук (`listen` на реальной сети, ~1 час) — §11, ручной шаг Джона после мержа, не в
  этой сессии и не в приёмке;
- правка `ethsc/evm.py`, `fingerprint.py`, `store.py`, `cluster.py`, `rpc.py`, `ingest.py`,
  `config.py`, `contour.yaml`, фикстур; новые фикстуры;
- повтор упавших `eth_getCode` в том же блоке, реорганизации цепи, WSS, `trace_*`,
  batch-запросы JSON-RPC (не в области ни этой, ни прошлой фазы);
- многопоточность/асинхронность CLI; цветной вывод; конфигурационный файл кроме `.env`;
  прогресс-бар;
- флаги риска (`SELFDESTRUCT`, `DELEGATECALL` и т.д.), MinHash/LSH, полный бэкфилл
  мейннета, keccak-`codeHash`, веб/API/бот — вне пруфа целиком (`plan.md` §6);
- гарантия, что `listen` переживёт падение процесса (нет демона, нет systemd-юнита, нет
  автоперезапуска) — только ручной запуск.

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
| карт в колоде | 3 (`test-helpers`, `cli` — `variants: 2`, `cli-judge`) |
| поколений | 2–3 (`test-helpers` → `cli` → возможно отдельно `cli-judge`; проверить в выводе `mrph plan`) |
| счёт исполнителя | $0.03–0.20 |
| карт с регенерацией | 0–2 |
| конфликтов `write-write` на preflight | 0 |
| тестов после | ≥ 164 + 8 (судья) + собственные тесты карт (≤ 10) |

**Опровергаемое утверждение фазы (Контур/приёмка):** `cli` проходит пробу
оркестратора не позже `r1` по логике (не по стражу текста — все стражи по `ast`); если
сгорит, разночтение сидит в месте, которое Контур не называет и это задание вводит впервые
здесь (§2.2): код выхода при `RpcError`, поведение `listen` между проходами, тонкость
`__main__.py`.

**Фальсифицируемое предсказание пруфа (`plan.md` §7, записано до смоука):** доля уникальных
L1-скелетов среди увиденных за час `listen` контрактов будет **< 30%** (клонов много).
Проверяется на выгрузке живого смоука §11, не на фикстурах.

## 10. Что записать в конце

Принято/сожжено карт, регенерации (что было в красном), минуты на поколение, счёт
провайдера, итоговое число тестов, доллары на принятую карту, имя ветки `morph/<run-id>`,
строка разведки (скаут не запускался — все цели новые файлы), статус сбоев Морфа.

## 11. Смоук после мержа (ручной шаг Джона, не в этой сессии)

Выполняется **после** того, как Джон смержил ветку `morph/<run-id>` в `master` и поставил
проектный `venv`. Не часть приёмки Морфа.

```bash
cd /home/john/Documents/Work2026/ETHSmartChecker
set -a; source .env; set +a   # настоящий INFURA_API_KEY, только в окружении процесса
venv/bin/python -m ethsc --db ethsc.sqlite listen --daily-budget 1000000
# через ~1 час: Ctrl-C (чистая остановка, код 0, прогресс сохранён)
venv/bin/python -m ethsc --db ethsc.sqlite clusters top --n 20
venv/bin/python -m ethsc --db ethsc.sqlite similar <адрес пары Uniswap V2, встреченной за час>
venv/bin/python -m ethsc --db ethsc.sqlite seed add <адрес известного скам-кода из посева> --label "<label>"
# затем продолжить listen ещё несколько минут и убедиться, что копия того же кода печатает ALERT
```

**Критерий успеха (совпадает с `plan.md` §7):**

1. в базе ≥ 1000 контрактов (`SELECT COUNT(*) FROM codes` или сумма `contracts` по проходам)
   и бюджет кредитов не превышен (нет ни одной строки `ALERT`/ошибки о превышении, процесс
   остановлен вручную, а не кодом 3);
2. `clusters top` показывает крупнейшие кластеры L0/L1, клоны EIP-1167 собраны по
   `proxy_target` (уровень `proxy` в выводе);
3. `similar <адрес пары Uniswap V2>` находит другие пары этой фабрики;
4. `seed add` на сид, затем при появлении его копии — строка `ALERT` с адресом, меткой и
   `score`;
5. **фальсифицируемое предсказание** §9: доля уникальных `skeleton_hash` среди всех
   увиденных `code_id` (не считая тех, что вошли только в кластеры уровня `proxy`) — менее
   30%. Считается вручную: `SELECT COUNT(DISTINCT skeleton_hash) * 1.0 / COUNT(*) FROM codes
   WHERE proxy_kind IS NULL`.

Если сид известного скама не найдётся, посев допустимо показать на безобидном семействе
(клоны Uniswap V2/V3) — решение Джона, как в `plan.md` §4.

## 12. Факт

Один ран, процессор glm (`z-ai/glm-5.3-flash`, StreamLake), 28.09.2026,
`--max-regenerations 6`. Ветка `morph/20260928-233057-2acaad84`, не смержена.

**Сбой самого Морфа перед раном (не колоды):** `.morph/deck.json` — один файл на весь проект,
не per-компонент; после фазы 4 в нём остались два зависших не выполненных до конца поколения
карты `ingest`/`ingest-judge` (`status: null`, наследие сожжённого рана 1 фазы 4, для которого
делался ручной `deck clear`+`reset`+повторный `plan --add` только на `ingest`, но финальный
`deck clear` после мержа никто не сделал). Мой `mrph plan --component cli --add` дописал 3
карты фазы 5 в ТОТ ЖЕ файл, не тронув старые. Первый `mrph run` (без `--component`, штатно —
такого флага у `run` нет) поднял все 5 карт, автопочинка зависимостей связала `test-helpers` с
`ingest` («читает `ethsc/ingest.py`, который пишет `ingest`»), и начал бы заново генерировать
уже смерженный `ethsc/ingest.py`. Остановлено на этапе отправки первой карты, до траты денег
(коммит `86eec0e8` — только сама колода, ни одной карты не принято). Восстановлено штатной
процедурой фазы 4: `git checkout master` → `mrph deck clear` → `mrph deck reset` →
`mrph plan --component cli --map morph-map.json --judge --add` — деку 3 карты, `mrph run`
запущен заново и прошёл чисто.

| величина | прогноз | факт |
|---|---|---|
| карт в колоде | 3 | 3 (`test-helpers`, `cli` — `variants: 2`, `cli-judge`) |
| поколений | 2–3 | 3: `test-helpers` → `cli` → `cli-judge` (стена ~6 минут) |
| принято / сожжено / пропущено | — | 3 / 0 / 0 |
| карт с регенерацией | 0–2 | 0 (`attempts: 1` у всех трёх); один вариант `cli.v1` отвергнут Морфом до приёмки — дважды блок `FILE: ethsc/cli.py` (тот же баг glm-flash, что в фазе 4) |
| запросов | — | 4 (`test-helpers`, `cli.v1`, `cli.v2`, `cli-judge`) |
| токены (вход/выход) | — | 103 405 / 16 246 |
| счёт исполнителя | $0.03–0.20 | **$0.0155** |
| долларов на принятую карту | — | $0.0052 |
| скаут | — | не запускался: все цели — новые файлы |
| `write-write` на preflight | 0 | 0 |
| тестов после | ≥ 164 + 8 + ≤10 своих | 176 (164 + 5 `test_cli.py` + 7 `test_cli_examples.py`; `test-helpers` своих тестов не пишет по стражу) |
| модули | — | `ethsc/cli.py` 239 строк, `ethsc/__main__.py` 6 строк, `tests/helpers.py` 129 строк, `tests/test_cli.py` 130 строк, `tests/test_cli_examples.py` 238 строк |

**Что было в красном:** ничего не было красным на приёмке. Единственная аномалия —
`cli.v1` отвергнут Морфом без запуска приёмки (дублированный блок `FILE:` в ответе glm-flash
на карте с 3 целями); `cli.v2` из того же поколения прошёл пробу с первого раза. Расхождение
с прогнозом §9 «не меньше 8 тестов судьи» — факт 7, не 8: карта `cli-judge` покрыла 4 примера
Контура плюс 3 дополнительных пункта §2.2 (бюджетная остановка, отказ без подкоманды, отказ на
плохом адресе) одним тестом на пункт, не размножая тесты искусственно ради числа; это была моя
формулировка ожидания, а не жёсткий страж приёмки (страж проверяет только полный `pytest`
зелёным, не минимум тестов у судьи) — впредь для такого числа стоит либо писать явный страж
«не меньше N», либо не давать точного числа в §9.

**Опровергаемое утверждение (§9):** подтверждено — карта `cli` прошла пробу оркестратора на
`r1` (`cli.v2`, первая же принятая приёмкой попытка), и ни одна красная попытка не была
вызвана стражем по тексту (красных попыток не было вовсе).

**Разведка:** скаут не запускался; колода тронула 5 новых файлов
(`ethsc/cli.py`, `ethsc/__main__.py`, `tests/helpers.py`, `tests/test_cli.py`,
`tests/test_cli_examples.py`), все из Контура/мапы, ни один существующий модуль не тронут.

**Долг Контура** (перенести в `contour.yaml`, каждая строка — самостоятельное уточнение):
1. `Command Line`: `main(argv=None, rpc=None, sleep=None) -> int`; `sleep=None` → `time.sleep`,
   инъецируется, чтобы цикл `listen` можно было остановить в тесте без реального ожидания.
2. `Command Line`: `listen` — цикл из повторных проходов `follow_chain` с `sleep(interval)`
   между ними (`--interval`, по умолчанию 12 с); `KeyboardInterrupt` вокруг `sleep` — чистая
   остановка, код 0; бюджетная/потолочная остановка внутри прохода — код 3, цикл завершается.
3. `Command Line`: коды выхода — 0 успех, 1 `RpcError` из `follow_chain` (сеть/бюджет ещё до
   первого прохода), 2 ошибка использования (`argparse`, неверный формат адреса, `seed add`
   на адрес без кода), 3 бюджетная/потолочная остановка после хотя бы одного прохода.
   `main` перехватывает ошибку `argparse` и возвращает её код как `int`, не поднимает
   `SystemExit`.
4. `Command Line`: строка алерта — `ALERT\t<address>\t<seed_address>\t<label>\t<score:.4f>`;
   все счётные значения на выводе форматируются `"%.4f"`.
5. `Command Line`: `clusters top [--n K]` (`K` по умолчанию 20) — `<level>\t<key>\t<len(members)>`
   по одной строке; `cluster <addr>` — `<level>\t<key>\t<members через запятую>`, 0 или 1
   строка; `seed list` — `<address>\t<label>`.
6. `Command Line`: формат адреса везде, где он позиционный аргумент — `^0x[0-9a-fA-F]{40}$`;
   несовпадение — код 2.

**Замечания к Морфу (передать автору):**
1. **Новое, важное:** `.morph/deck.json` — один файл на весь проект без per-фазовой изоляции;
   карты, не доведённые до `written`/`failed` явного терминала (оставшиеся `status: null`
   после ручного `deck clear`+`reset` для частичного перезапуска), переживают мерж ветки и
   молча попадают в следующий `plan --add`, а `mrph run` не имеет флага «только этот
   компонент» — запускает весь backlog. Смотри воспроизведение выше (§12, «Сбой самого Морфа
   перед раном»). Не обошёл молча: остановил ран до трат, откатился, сделал
   `deck clear`+`reset`+`plan --add` заново.
2. Ключ мапы `cards.*` — имя ГРУППЫ Контура, а не производное от имени функции: карты, названные
   `command-line`/`command-line-judge` (по имени функции `Command Line`), молча
   игнорировались планировщиком, который откатывался к полным дефолтам без моего
   `context_slice`/`acceptance`/`instruction`. Переименование в `cli`/`cli-judge` (имя группы)
   исправило это. Стоит явно задокументировать эту конвенцию, а не давать угадывать по
   прежним колодам.
3. Явный `depends_on` на `<id>-judge`-карте в мапе ЗАМЕНЯЕТ, а не дополняет подразумеваемую по
   умолчанию зависимость судьи от своей кодовой карты: без явного `depends_on` судья сама
   встаёт в поколение после кода; с явным (в моём случае — только `["test-helpers"]`) она
   потеряла зависимость от `cli` и попала бы в одно поколение с ним (риск чтения ещё не
   записанного `ethsc/cli.py`). Пришлось писать `depends_on: ["test-helpers", "cli"]` явно.
4. `mrph run` при штатном завершении создаёт в `docs/` два untracked SVG
   (`contour.svg`, `contour-detailed.svg`) — судя по всему, побочная визуализация Контура;
   не запрашивалась, не задокументирована, не закоммичена (оставлена как есть).
5. Три предыдущих замечания из фазы 4 подтверждены неизменными: судья читает срез и приёмку
   из мапы (`map.cards["<id>-judge"]`) — работает; `extra_cards` без `"component"` попал бы в
   каждую колоду — не проверялось повторно, но `test-helpers` с `"component": "cli"` встал
   верно; после `mrph run` checkout остаётся на `morph/<run-id>` — вернул на `master` руками.

Сколько раз критерий менялся после первого красного: 0 (красных не было). Ветка рана:
`morph/20260928-233057-2acaad84`.
