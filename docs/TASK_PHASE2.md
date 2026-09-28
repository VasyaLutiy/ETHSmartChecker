# Задача для Морфа, фаза 2: компоненты `fingerprint` и `store`

> Дата: 28.09.2026. Проект ETHSmartChecker, план — `plan.md` §5, фаза 2.
> Запись системы — `contour.yaml`, компоненты `fingerprint` (2 Function) и `store`
> (4 Function, Data Object `Code Database`). Контур в этой фазе не меняется.
> Фикстуры — `tests/fixtures/`, опись — `tests/fixtures/README.md`. Новых фикстур нет.
> Разбивки на карты здесь нет.

## 1. Зачем это

После фазы 1 в проекте есть только `ethsc/evm.py` (120 строк, 45 тестов). Анализ
байткода ничего не помнит и ничего не сравнивает:

- в блоке 26077729 (`tests/fixtures/codes_26077729.json`) 206 кандидатов, 147 с кодом,
  но 130 разных кодов: без `code_id` одинаковый код хранится и анализируется
  повторно. Четыре пары UniswapV2Pair этого блока — один код, 11 293 байта;
- 8 пулов Uniswap V3 и 5 LaunchToken различаются побайтово, а скелет у них сводится к
  двум семействам. Сравнить их можно только по `skeleton_hash`, которого ещё нет;
- копия ханипота BELLE (`code_belle_copy_1807090d.hex`) отличается от сида одним
  селектором из 15: L2-похожесть 13/15 = 0.8667 — это и есть алерт фазы 3, и
  посчитать её сейчас нечем;
- фазам 3–5 (кластеры, приём, CLI) нужны база, прогресс, watchlist и счётчик
  кредитов: без `store` листенер не переживёт перезапуск и не удержит бюджет
  3M кредитов в сутки (блок 26077729 стоит 1000 + 206·80 = 17 480 кредитов).

## 2. Контракт

### 2.1. Формы ВХОДНЫХ данных

| форма | где определена | как построить в тесте |
|---|---|---|
| Runtime Code, `bytes` | `contour.yaml`, Data Object `Runtime Code` (компонент `evm`) | `bytes.fromhex(open(p).read().strip()[2:])` для `p` из `tests/fixtures/code_*.hex` |
| код кандидата блока | `tests/fixtures/codes_26077729.json`: `{address: "0x…"}`, 206 ключей, адреса строчные, отсортированы; 59 значений — `"0x"` (нет кода) | `bytes.fromhex(v[2:])`; `v == "0x"` → аккаунт без кода, `code_id` `None` |
| адрес | строка `"0x"` + 40 hex, регистр любой (в README — checksum, в JSON — строчные) | литерал из README или ключ JSON |
| путь базы | строка пути к файлу SQLite | `os.path.join(tempfile.mkdtemp(), "t.db")`; `":memory:"` в примерах не используется |
| функции `evm` | `ethsc/evm.py`: `disassemble` :11, `strip_metadata` :38, `extract_selectors` :59, `detect_proxy` :80, `build_skeleton` :97 | вызываются, не строятся; `evm.py` не меняется |
| Fingerprint | `contour.yaml`, Data Object `Fingerprint` (компонент `fingerprint`) | только через `fingerprint(code)`; `store` его не конструирует вручную |

### 2.2. Формы ВЫХОДНЫХ данных

`ethsc/fingerprint.py`:

- `fingerprint(code: bytes)` → `None` для `b""`, иначе `dict` ровно с пятью ключами:
  `code_id` (`hashlib.sha256(code).hexdigest()`, 64 строчных hex), `size` (`int`,
  `len(code)`), `skeleton_hash` (`sha256(build_skeleton(code)).hexdigest()`),
  `selectors` (`extract_selectors(code)`, отсортированный `list` строк), `proxy`
  (`detect_proxy(code)`: `dict` `{"kind", "target"}` или `None`). На мусорных байтах
  возвращает `dict`, не бросает.
- `similarity(code_a: bytes, code_b: bytes)` → `float` в `[0, 1]`: Жаккар множеств
  селекторов, если оба непусты; иначе Жаккар множеств 3-грамм опкодов (кортежи из трёх
  подряд идущих `op` из `disassemble(strip_metadata(code)[0])`, аргументы отброшены).
  Оба множества пусты → `0.0`; это правило сильнее «идентичный код даёт 1.0», поэтому
  `similarity(b"", b"") == 0.0`. Симметрична: `similarity(a, b) == similarity(b, a)`
  точно, не приблизительно.

`ethsc/store.py`, класс `Store`:

- `Store(path)` открывает или создаёт файл (`CREATE TABLE IF NOT EXISTS`) со схемой
  `Code Database` из `contour.yaml` дословно: таблицы `codes`, `addresses`,
  `progress`, `seeds`, `ledger`, колонки в указанном порядке; `codes.selectors` —
  JSON-список (`json.dumps`), `proxy_kind`/`proxy_target` — `NULL` без прокси.
- Каждый пишущий метод коммитит до возврата: второе соединение `sqlite3` к тому же
  файлу сразу видит строки. `close()` закрывает соединение; `Store(path)` после
  `close()` видит всё записанное.
- Адреса нормализуются в нижний регистр на ВХОДЕ каждого метода (`put_address`,
  `has_address`, `code_of`, `add_seed`) и хранятся строчными.
- `put_code(code)` → `code_id` (`str`); повторный вызов с тем же кодом возвращает тот
  же `code_id`, строк не добавляет, не бросает.
- `put_address(address, code_id, block)` → `None`; известный адрес не меняется
  (первая запись выигрывает), не бросает. `code_id` может быть `None` (EOA).
- `has_address(address)` → `bool`. `code_of(address)` → `bytes` кода или `None`
  (адрес без кода или неизвестный адрес). `addresses_of(code_id)` →
  отсортированный `list` строчных адресов, `[]` для неизвестного `code_id`.
- `get_progress()` → `int` или `None`; `set_progress(block)` → `None`, перезаписывает.
- `add_seed(address, label)` → `None`; адрес без сохранённого кода (неизвестный или
  с `code_id` `None`) → `KeyError(address)`; повтор по адресу оставляет одну запись с
  последним `label`. `seeds()` → `list` из `dict` ровно с ключами `address`, `label`,
  `code_id`, отсортирован по `address`.
- `spend(day, method, credits)` → `None`, добавляет строку в `ledger`;
  `spent(day)` → `int`, сумма за день, `0` для дня без записей.

### 2.3. Имена

- Модули: `ethsc/fingerprint.py` (функции `fingerprint`, `similarity`),
  `ethsc/store.py` (класс `Store`, методы `put_code`, `put_address`, `has_address`,
  `code_of`, `addresses_of`, `get_progress`, `set_progress`, `add_seed`, `seeds`,
  `spend`, `spent`, `close`).
- `close` — единственное имя, которого нет в `contour.yaml`: пример «the db file
  closed and reopened» требует метода, а запись его не называет.
- Тесты кодовых карт: `tests/test_fingerprint.py`, `tests/test_store.py`; тесты судей:
  `tests/test_fingerprint_examples.py`, `tests/test_store_examples.py`.
- Ключ Fingerprint и столбцы таблиц — дословно из Data Object `Fingerprint` и
  `Code Database`. Числа — из `examples` `contour.yaml`; все проверены оркестратором по
  фикстурам 28.09 (sha256, 27/11/32/14/15 селекторов, 9/34, 9/29, 13/15, 22 3-граммы у
  клона, 4 адреса с `code_id` 8b5db55f… в блоке, 1000 + 80·206 = 17 480).

### 2.4. Что не должно сломаться

`ethsc/evm.py`, `ethsc/__init__.py` (пустой), `tests/test_evm.py`,
`tests/test_evm_examples.py` — байт в байт; 45 тестов фазы 1 зелёные.
`contour.yaml`, `plan.md`, `tests/fixtures/*` не трогаются. `fingerprint` импортирует
`ethsc.evm`, `store` импортирует `ethsc.fingerprint`; обратных импортов нет.

## 3. Приёмка

Базовая линия: 45 тестов (`45 passed`).

1. **Кодовая карта `fingerprint`** (`ethsc/fingerprint.py` + `tests/test_fingerprint.py`),
   ступени от узкой к широкой:
   1. `ast.parse(..., feature_version=(3,9))` по обоим файлам;
   2. страж Stdlib Only / No Network In Core:
      `grep -nE '^[[:space:]]*(import|from)[[:space:]]+(urllib|http|socket|requests|sqlite3|yaml|numpy|pandas|Crypto|eth_|web3)' ethsc/fingerprint.py`
      пуст, иначе `exit 1` с сообщением;
   3. **проба оркестратора** — inline-скрипт: по проверке на каждый из 8 examples
      компонента (4 Fingerprint Code, 4 Similarity Score), плюс точный набор ключей и
      поля `skeleton_hash`/`selectors`/`proxy` против функций `evm`, `proxy` клона,
      симметрия и `type(...) is float`, `similarity(W, W) == 1.0`,
      `similarity(b"", b"") == 0.0`, «не бросает» на трёх мусорных входах. Печатает
      `<Function> <N>: got …, want …` по каждому расхождению;
   4. `venv/bin/python -m pytest tests/test_fingerprint.py -q --tb=short`;
   5. `venv/bin/python -m pytest tests -q --tb=short`.
2. **Кодовая карта `store`** (`ethsc/store.py` + `tests/test_store.py`):
   1. `ast.parse` по обоим файлам;
   2. страж: тот же `grep` без `sqlite3` в списке, по `ethsc/store.py`;
   3. **проба оркестратора** на временной базе: по проверке на каждый из 7 examples
      компонента (3 Store Codes And Contracts, 1 Track Progress, 2 Manage Watchlist,
      1 Budget Ledger), плюс: адреса подаются в смешанном регистре и в обратном
      порядке; счёт строк `codes`/`addresses` вторым соединением `sqlite3` до
      `close()`; имена таблиц и столбцы `codes` через `PRAGMA table_info`;
      `json.loads(selectors)` и `proxy_kind`/`proxy_target` клона в строке `codes`;
      повторные `put_code`/`put_address` ничего не меняют; `seeds()` отсортирован по
      адресу при вставке в обратном порядке; `KeyError` на неизвестный адрес и на EOA;
      `spent` возвращает `int`;
   4. `venv/bin/python -m pytest tests/test_store.py -q --tb=short`;
   5. `venv/bin/python -m pytest tests -q --tb=short`.
3. **Карты судей** (`tests/test_fingerprint_examples.py`, `tests/test_store_examples.py`,
   по тесту на example, код не трогают): `ast.parse`, затем свой файл
   `pytest … -q --tb=short`, затем `pytest tests -q --tb=short`.
4. Итог фазы: полный `venv/bin/python -m pytest -q --tb=short` зелёный, в нём
   45 тестов фазы 1 и не меньше 15 тестов судей (8 + 7).

Каждая приёмка обёрнута в снимок `/tmp/morph/<card>/` с логом `acc-<время>-<pid>.log`
и возвращает код своей цепочки. Эталонной реализации нет: приёмки прогнаны вручную и
обязаны быть красными на отсутствующем модуле (`ast.parse`), на пустом модуле
(`ImportError` в пробе) и на мутациях (прописные hex в `code_id`, `size` тела вместо
кода, Жаккар без симметрии; `addresses_of` без сортировки, адрес без `lower()`, запись
без `commit`).

Тесты пишутся на `unittest`, у каждого assert есть `msg=`. В классах, которые сравнивают
списки, словари или байты, стоит `maxDiff = None`. Базы — только во временных каталогах,
ни одного файла в дереве проекта.

## 4. Ограничения

- Python 3.12 в рантайме, синтаксис совместим с 3.9, только стандартная библиотека
  (`hashlib`, `json`, `sqlite3`, `typing`).
- Оба модуля новые: рамка правки существующего файла к ним не применяется.
- Один файл — одна карта-владелец. Судья пишет только свой тест.
- `fingerprint` без ввода-вывода: не читает файлы, не печатает, не ходит в сеть, не
  импортирует `sqlite3`. `store` пишет только в файл, переданный в `Store(path)`.
- No Network In Core: ни `urllib`, ни `http`, ни `socket` ни в одном из модулей.
- Deterministic Output: всё, что возвращает список, отсортировано; порядок вставки не
  влияет на ответ.
- `store` читает `fingerprint` физически (импорт), значит работает только после неё.
- Во время рана дерево не трогается: правка файла из среза даёт `stale-context`.

## 5–6. Техники; что не указано

Как в TASK_TEMPLATE. Не указаны: индексы, `PRAGMA`, режим журнала, пул соединений,
контекстный менеджер у `Store` — на усмотрение исполнителя, если приёмка зелёная.
Разбивка на карты, срезы и формулировки приёмки — дело оркестратора.

## 7. Вне области

- компоненты `cluster`, `rpc`, `ingest`, `cli` и `ethsc/config.py` (фазы 3–5);
- чтение кодов и отпечатков пачкой (итерация по `codes`, выборка по `skeleton_hash`,
  `proxy_target`) — это API кластеризации фазы 3;
- поведение `put_code(b"")` и `put_address` с `code_id`, которого нет в `codes`: в
  записи не заданы, не тестируются;
- `similarity` поверх базы, пороги, n-граммы кроме 3, MinHash/LSH;
- проверка `Budget Respected` (лимит до вызова) — это `rpc`/`ingest`; `store` только
  считает;
- keccak/`codeHash`, миграции схемы, конкурентный доступ из нескольких процессов;
- правка `ethsc/evm.py`, `contour.yaml`, фикстур; новые фикстуры; любая сеть.

## 8. Как запускать

```bash
cd /home/john/Documents/Work2026/ETHSmartChecker
set -a; source /home/john/Documents/Work2026/MorphProject/morph-lab/.env; set +a
~/Documents/python_venv/venv_mrph/bin/mrph deck check --root .
~/Documents/python_venv/venv_mrph/bin/mrph run --root . --processor glm --max-regenerations 4 --pretty
```

Исполнитель — `glm` (route sync). Перед стартом дерево чистое.

## 9. Пререгистрация

| величина | прогноз |
|---|---|
| карт в колоде | 4 (`fingerprint`, `store` c `variants: 2`; `fingerprint-judge`, `store-judge`) |
| поколений | 3 (`fingerprint` → `fingerprint-judge`, `store` → `store-judge`) |
| счёт исполнителя | $0.02–0.30 |
| карт с регенерацией | 0–1 |
| конфликтов `write-write` на preflight | 0 |
| тестов после | ≥ 45 + 15 (судьи) + собственные тесты карт |

**Опровергаемое утверждение:** как и в фазе 1, проба в приёмке точнее судьи: код,
прошедший пробу, проходит тесты обоих судей с первой попытки. Если судья `store`
сгорит, разночтение сидит в месте, которое `contour.yaml` не называет (закрытие базы,
регистр адреса, `KeyError` на EOA), и его надо внести в Контур.

## 10. Что записать в конце

Принято/сожжено карт, регенерации (что было в красном), минуты на поколение, счёт
провайдера, итоговое число тестов, доллары на принятую карту, имя ветки
`morph/<run-id>`.

## 11. Факт

Ран `20260928-204726-d78a00e6`, ветка `morph/20260928-204726-d78a00e6` (не смержена),
процессор glm (z-ai/glm-5.3-flash, sync), 28.09.2026, `--max-regenerations 4`, потолок $1.

| величина | прогноз | факт |
|---|---|---|
| карт в колоде | 4 | 4 (`fingerprint`, `fingerprint-judge`, `store`, `store-judge`) |
| поколений | 3 | 3, стена 4 мин 17 с (20:47:26 → 20:51:43) |
| принято / сожжено / пропущено | — | 4 / 0 / 0 |
| регенераций | 0–1 | 0 (`attempts 1` у всех) |
| вариантов `fingerprint` | 2 | `fingerprint.v1` красный, `fingerprint.v2` принят |
| вариантов `store` | 2 | `store.v1` принят первым |
| запросов | 6 | 6 |
| токены | — | 90 939 вход / 21 098 выход |
| счёт исполнителя | $0.02–0.30 | **$0.0171** (ниже прогноза) |
| долларов на принятую карту | — | $0.0043 |
| счёт скаута (отдельный бюджет) | — | $0.0326, 9 раундов, ~24 мин стены |
| `write-write` на preflight | 0 | 0 |
| тестов после | ≥ 45 + 15 + свои | 89: 45 фазы 1 + 15 судей (8 + 7) + 29 своих (13 + 16), `pytest -q` зелёный |
| модули | — | `ethsc/fingerprint.py` 72 строки, `ethsc/store.py` 196; импорты `hashlib`, `json`, `sqlite3`, `typing`, `ethsc.*` |

**Что было в первом красном.** Проба оркестратора `fingerprint.v1` прошла, упал
собственный тест исполнителя: хелпер `test_code(fname)` в `tests/test_fingerprint.py`
pytest собрал как тест (`fixture 'fname' not found`, 13 passed, 1 error). Ошибка в
тестовом файле, а не в коде. Вариант `v2` из того же батча зелёный, регенерация не
понадобилась.

**Опровергаемое утверждение подтверждено:** код, прошедший пробу, прошёл тесты обоих
судей с первой попытки (8/8 и 7/7).

**Разведка:** скаут назвал 1 файл (`morph-map.json`), колода записала 4 новых файла
и 2 теста судей. Все шесть взяты из Контура и мапы: у фазы, которая только создаёт
файлы, скаут их не видит.

**Долг Контура:** `Store.close()` задан только в этой спеке (§2.3), в `contour.yaml`
его нет. Внести в Function `Store Codes And Contracts` при следующей правке Контура.
Туда же: нормализация регистра адреса на входе, commit до возврата, `KeyError` на
EOA в `add_seed`, `similarity(b"", b"") == 0.0`.

**Сбой Морфа (передан автору):** `mrph plan --spec contour.yaml --component fingerprint
--map morph-map.json --judge` → exit 4,
`{"error":{"code":4,"kind":"PlanError","message":"group 'evm' names unknown Function 'Disassemble'"}}`:
группы других компонентов в общей мапе отклоняются. После фильтрации мапы
`depends_on: ["fingerprint"]` у `store` → exit 4,
`card 'store' depends on unknown fingerprint`. Обход: по одной отфильтрованной мапе
на компонент (`.morph/map_<c>.json`), ребро `store → fingerprint` добавлено при
слиянии колоды.
