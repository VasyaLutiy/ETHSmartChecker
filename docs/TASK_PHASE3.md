# Задача для Морфа, фаза 3: компонент `cluster`

> Дата: 28.09.2026. Проект ETHSmartChecker, план — `plan.md` §5, фаза 3.
> Запись системы — `contour.yaml`, компонент `cluster` (3 Function: `Build Clusters`,
> `Find Similar`, `Match Watchlist`; Data Object `Cluster`, `Alert`). Контур в этой
> фазе не меняется. Фикстуры — `tests/fixtures/`, опись — `tests/fixtures/README.md`.
> Новых фикстур нет, сеть не нужна. Разбивки на карты здесь нет.

## 1. Зачем это

После фазы 2 база умеет хранить код, но ничего не группирует и не ищет:

- в блоке 26077729 (`tests/fixtures/codes_26077729.json`) 147 адресов с кодом и 130
  разных `code_id`. Кластеров там 15 — 7 L0 (4 UniswapV2Pair на одном коде и шесть
  пар), 2 L1 (8 пулов Uniswap V3 и 5 LaunchToken: разные байты, один скелет), 6 proxy
  (2 цели EIP-1167 и 4 цели EIP-7702). Сейчас их не видно ни одним вызовом;
- копия ханипота BELLE (`code_belle_copy_1807090d.hex`) похожа на сид на 13/15 =
  0.8667, а WETH9 — на 9/16 = 0.5625. Функции, которая по сиду поднимает алерт
  на первую и молчит на вторую, нет — это и есть цель проекта по безопасности;
- публичный API `Store` не умеет перечислить сохранённые коды и отдать код по
  `code_id`: `code_of` работает только от адреса, `addresses_of` — от известного
  `code_id`. Фаза 2 (§7) сознательно отложила чтение пачкой сюда. Без него
  кластеризация полезла бы в приватное `Store._conn` и в SQL мимо `store`;
- фазы 4–5 (`ingest` зовёт `match_watchlist` на каждый новый код, `cli` печатает
  `clusters top`, `similar`) строятся на этих трёх функциях.

## 2. Контракт

### 2.1. Формы ВХОДНЫХ данных

| форма | где определена | как построить в тесте |
|---|---|---|
| Runtime Code, `bytes` | `contour.yaml`, Data Object `Runtime Code` (компонент `evm`) | `bytes.fromhex(open(p).read().strip()[2:])` для `p` из `tests/fixtures/code_*.hex` |
| код кандидата блока | `tests/fixtures/codes_26077729.json`: `{address: "0x…"}`, 206 ключей, строчные; 59 значений `"0x"` | `v == "0x"` → `put_address(a, None, 26077729)`; иначе `put_address(a, put_code(bytes.fromhex(v[2:])), 26077729)` |
| `Store` | `ethsc/store.py:49` (строки до правки фазы 3); `put_code` :63, `put_address` :88, `code_of` :110, `addresses_of` :121, `add_seed` :150, `seeds` :170, `close` :57 | `Store(os.path.join(tempfile.mkdtemp(), "t.db"))`, наполнить вызовами выше |
| Fingerprint | `contour.yaml`, Data Object `Fingerprint`; `ethsc/fingerprint.py:21` | только `fingerprint(code)`; вручную не строится |
| `similarity` | `ethsc/fingerprint.py:53` | вызывается, не строится; `fingerprint.py` не меняется |
| адреса BELLE и копий | `tests/fixtures/README.md` строки 23–27 | литералы: сид `0x34c6211621f2763c60eb007dc2ae91090a2d22f6`, копии `0x1807090d…0385`, `0x2141be5f…39f5`, `0x46cadea5…8f0a`, `0x6411bed8…eb8c` |

### 2.2. Формы ВЫХОДНЫХ данных

`ethsc/store.py`, класс `Store`, два новых метода (чтение пачкой):

- `fingerprints()` → `list` из `dict` Fingerprint (ровно ключи `code_id`, `size`,
  `skeleton_hash`, `selectors`, `proxy`) по одному на каждую строку `codes`,
  отсортирован по `code_id`. Каждый элемент равен `fingerprint(code)` этого кода:
  `selectors` — `list` (из `json.loads`), `proxy` — `{"kind", "target"}` или `None`.
  Пустая база → `[]`.
- `code_by_id(code_id)` → `bytes` сохранённого кода или `None` для неизвестного
  `code_id`.
- Остальные методы `Store` и схема `Code Database` не меняются.

`ethsc/cluster.py`:

- `build_clusters(store)` → `list` из `dict` Cluster ровно с ключами `level`, `key`,
  `members`:
  - `L0`: по `code_id` непрокси-кода, у которого ≥ 2 адреса; `key` — `code_id`;
  - `L1`: по `skeleton_hash`, общему у ≥ 2 разных `code_id` непрокси-кодов; `key` —
    `skeleton_hash`; `members` — все адреса всех этих кодов;
  - `proxy`: по паре (`kind`, `target`) прокси-кодов, у которой ≥ 2 адреса (по всем
    кодам с этой парой); `key` — `"<kind>:<target>"`, например
    `"eip1167:0x4181f37093e3a21a4e0d5ef355c5b1938cba5bfb"`;
  - прокси-код (`proxy` не `None`: `eip1167`, `eip7702`) входит только в `proxy`;
  - `members` — отсортированный `list` строчных адресов; адреса без кода не входят;
  - список отсортирован: число членов по убыванию, затем уровень `L0` < `L1` <
    `proxy`, затем `key` по возрастанию. Порядок вставки в базу на ответ не влияет.
- `find_similar(store, address, min_score=0.8)` → `list` кортежей `(address, score)`:
  каждый другой адрес с кодом, у которого `similarity(код запроса, его код) >=
  min_score`; сам запрошенный адрес не входит, адреса того же кода входят с `1.0`.
  Полный перебор: одна `similarity` на каждый `code_id`, результат раздаётся его
  адресам. Сортировка: `score` по убыванию, затем адрес. Адрес запроса в любом
  регистре; неизвестный адрес или адрес без кода → `[]`.
- `match_watchlist(store, code, min_score=0.8)` → `list` из `dict` Alert ровно с
  ключами `seed_address`, `label`, `score`: по одному на каждый сид из
  `store.seeds()`, у кода которого `similarity(code, код сида) >= min_score`.
  Сортировка: `score` по убыванию, затем `seed_address`. Без сидов, на `b""` и на
  мусорных байтах — `[]` или список, никогда исключение.
- `score` везде — `float` прямо из `similarity`, без округления:
  `13/15`, `26/32`, `9/16` сравниваются точно.

### 2.3. Имена

- Модуль `ethsc/cluster.py`: функции `build_clusters`, `find_similar`,
  `match_watchlist`; значения `level` — строки `"L0"`, `"L1"`, `"proxy"`.
- Новые методы `Store`: `fingerprints`, `code_by_id`. Их нет в `contour.yaml`
  (долг Контура, §11): Function `Build Clusters` говорит «uses: store», но API
  чтения пачкой запись не называет.
- Тесты: `tests/test_store_read.py` (новые методы `Store`), `tests/test_cluster.py`
  (кодовая карта), `tests/test_cluster_examples.py` (судья).
- Числа — из `examples` `contour.yaml`, проверены оркестратором по фикстурам 28.09
  через `fingerprint`/`similarity` фазы 2: 206/147/130; L0 размеры 4,2,2,2,2,2,2 и
  ключи; L1 8 и 5 адресов; 6 proxy (3, 3, 2, 2, 2, 2); `find_similar` 3×1.0 и
  26/32; 4 копии BELLE по 13/15; WETH9 против BELLE 9/16; 12 прокси-кодов из 130.

### 2.4. Что не должно сломаться

`ethsc/evm.py`, `ethsc/fingerprint.py`, `ethsc/__init__.py` и все восемь тестовых
файлов фаз 1–2 — байт в байт; 89 тестов зелёные. В `ethsc/store.py` правка только
добавляющая: существующие методы и `_SCHEMA` не меняются. `contour.yaml`, `plan.md`,
`tests/fixtures/*` не трогаются. `cluster` импортирует `ethsc.fingerprint` и работает
с `Store` через переданный объект; `store` не импортирует `cluster`.

## 3. Приёмка

Базовая линия: 89 тестов (`89 passed`).

1. **Кодовая карта чтения пачкой** (`ethsc/store.py` + `tests/test_store_read.py`):
   1. `ast.parse(..., feature_version=(3,9))` по обоим файлам;
   2. страж рамки правки: `git diff --numstat f175196 -- ethsc/store.py` — не больше
      90 вставленных и не больше 3 удалённых строк, иначе `exit 1` с сообщением;
   3. страж Stdlib Only / No Network In Core: тот же `grep` импортов, что в фазе 2,
      по `ethsc/store.py`;
   4. **проба оркестратора** на временных базах: `fingerprints()` пустой базы `[]`;
      три кода (WETH9, клон EIP-1167, BELLE), вставленные в обратном порядке, дают
      ровно `sorted([fingerprint(c)…], key=code_id)` (типы, ключи, `proxy` клона);
      `code_by_id` → те же `bytes`, `None` на неизвестный; повторный `put_code` не
      дублирует; то же после `close()` и переоткрытия; база блока 26077729 —
      130 отпечатков, 12 с прокси, упорядочены по `code_id`, отпечаток `8b5db55f…`
      равен `fingerprint` кода `0xb4e16d01…`; `addresses_of`/`code_of` работают как
      прежде;
   5. `venv/bin/python -m pytest tests/test_store_read.py tests/test_store.py tests/test_store_examples.py -q --tb=short`;
   6. `venv/bin/python -m pytest tests -q --tb=short`.
2. **Кодовая карта `cluster`** (`ethsc/cluster.py` + `tests/test_cluster.py`):
   1. `ast.parse` по обоим файлам;
   2. страж: `grep` импортов `urllib|http|socket|requests|sqlite3|yaml|numpy|pandas|Crypto|eth_|web3`
      и обращения `_conn` в `ethsc/cluster.py` пуст — только публичный API `Store`;
   3. **проба оркестратора**: база блока 26077729 — все 15 кластеров списком
      `(level, key, число членов)` в точном порядке (по проверке на каждый из
      3 examples Build Clusters, плюс ровно ключи `level`/`key`/`members`, члены
      отсортированы и строчные, члены прокси `eip1167:0x4181…`, база с обратным
      порядком вставки даёт равный список, пустая база → `[]`); Find Similar 1
      точным списком кортежей, тот же ответ на адрес в верхнем регистре,
      `min_score=1.0` оставляет три адреса, неизвестный адрес и EOA → `[]`,
      `score` — `float`; Find Similar 2 на базе BELLE + 4 копии + WETH9; Match
      Watchlist 1–3 точными `dict`, плюс `min_score=0.5` даёт WETH9 алерт 9/16, два
      сида сортируются по `score`, три мусорных входа не бросают. Печатает
      `<Function> <N>: got …, want …` по каждому расхождению;
   4. `venv/bin/python -m pytest tests/test_cluster.py -q --tb=short`;
   5. `venv/bin/python -m pytest tests -q --tb=short`.
3. **Карта судьи** (`tests/test_cluster_examples.py`, по тесту на example, код не
   трогает): `ast.parse`, затем свой файл `pytest … -q --tb=short`, затем
   `pytest tests -q --tb=short`.
4. Итог фазы: полный `venv/bin/python -m pytest -q --tb=short` зелёный, в нём 89
   тестов фаз 1–2 и не меньше 8 тестов судьи (3 + 2 + 3).

Каждая приёмка обёрнута в снимок `/tmp/morph/<card>/` с логом `acc-<время>-<pid>.log`
и возвращает код своей цепочки. Эталонной реализации нет: приёмки прогнаны вручную и
красные на отсутствующем модуле/методе, на пустом модуле (`ImportError` в пробе), на
заглушках, возвращающих `[]`/`None`, и на заглушках, бросающих исключение.

Тесты пишутся на `unittest`, у каждого assert есть `msg=`. В классах, которые сравнивают
списки, словари или байты, стоит `maxDiff = None`. Базы — только во временных каталогах,
ни одного файла в дереве проекта. Хелперы тестов не называются `test_*` (фаза 2, §11:
pytest собрал `test_code(fname)` как тест).

## 4. Ограничения

- Python 3.12 в рантайме, синтаксис совместим с 3.9, только стандартная библиотека.
- `ethsc/store.py` (196 строк) — существующий файл: правка в рамке 20–60 строк,
  только добавление двух методов (и их докстрингов); страж — не больше 90/3.
  `ethsc/cluster.py`, `tests/test_store_read.py`, `tests/test_cluster.py` — новые.
- Один файл — одна карта-владелец. Судья пишет только свой тест.
- `cluster` без ввода-вывода кроме вызовов `Store`: не импортирует `sqlite3`, не
  трогает `store._conn`, не печатает, не ходит в сеть.
- No Network In Core: ни `urllib`, ни `http`, ни `socket`.
- Deterministic Output: каждый список полностью упорядочен, порядок вставки не влияет.
- `cluster` физически читает новые методы `store` — работает только после них.
- Во время рана дерево не трогается: правка файла из среза даёт `stale-context`.

## 5–6. Техники; что не указано

Как в TASK_TEMPLATE. Не указаны: место новых методов внутри класса `Store`, SQL
чтения, кэш кодов внутри `find_similar`, внутренние хелперы `cluster` — на усмотрение
исполнителя, если приёмка зелёная.

## 7. Вне области

- компоненты `rpc`, `ingest`, `cli` и `ethsc/config.py` (фазы 4–5); вызов
  `match_watchlist` из приёма и строки `ALERT`;
- индекс L2 (MinHash/LSH, n-граммы кроме 3, предфильтр по размеру): только полный
  перебор по `code_id`;
- кластеры L2 (транзитивные группы по похожести) и «top N» — это `cli clusters top`;
- `find_similar` по сырому коду вместо адреса, пороги кроме `min_score`, похожесть
  прокси на его implementation (разворачивание прокси);
- любые изменения существующих методов `Store`, схемы `Code Database`, индексы, миграции;
- кэширование кластеров в базе, инкрементальная пересборка;
- правка `ethsc/evm.py`, `ethsc/fingerprint.py`, `contour.yaml`, фикстур; новые
  фикстуры; любая сеть.

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
| карт в колоде | 3 (`store-read`, `cluster` c `variants: 2`, `cluster-judge`) |
| поколений | 3 (`store-read` → `cluster` → `cluster-judge`) |
| счёт исполнителя | $0.01–0.15 |
| карт с регенерацией | 0–1 |
| конфликтов `write-write` на preflight | 0 |
| правка `ethsc/store.py` | +20…+60, 0 удалений |
| тестов после | ≥ 89 + 8 (судья) + собственные тесты карт |

**Опровергаемое утверждение:** правка существующего файла в рамке 20–60 строк
проходит с первой попытки так же, как новые файлы фаз 1–2, а код `cluster`,
прошедший пробу, проходит судью с первой попытки. Если судья сгорит, разночтение
сидит в месте, которое `contour.yaml` не называет (прокси вне L0/L1, члены L1 —
адреса, а не коды, самоисключение в `find_similar`), и его надо внести в Контур.

## 10. Что записать в конце

Принято/сожжено карт, регенерации (что было в красном), минуты на поколение, счёт
провайдера, итоговое число тестов, доллары на принятую карту, фактическая рамка
правки `store.py`, имя ветки `morph/<run-id>`, строка разведки (скаут назвал / колода
тронула / добавил оркестратор).

## 11. Факт

Ран `20260928-210713-5a3d4661`, ветка `morph/20260928-210713-5a3d4661` (не смержена),
процессор glm (z-ai/glm-5.3-flash, sync), 28.09.2026, `--max-regenerations 4`, потолок $1.

| величина | прогноз | факт |
|---|---|---|
| карт в колоде | 3 | 3 (`store-read`, `cluster`, `cluster-judge`) |
| поколений | 3 | 3, стена 11 мин 33 с (21:07:13 → 21:18:46): 2:03, 6:18, 3:12 |
| принято / сожжено / пропущено | — | 3 / 0 / 0 |
| карт с регенерацией | 0–1 | **3** (`attempts 2` у всех, все прошли на `r1`) |
| запросов | 4 | 8 (1+1, 2+2 варианта, 1+1) |
| токены | — | 142 566 вход / 40 865 выход |
| счёт исполнителя | $0.01–0.15 | **$0.0322** |
| долларов на принятую карту | — | $0.0107 |
| счёт скаута (отдельный бюджет) | — | $0.0173, 5 вызовов, 1 поправка ответа |
| `write-write` на preflight | 0 | 0 |
| правка `ethsc/store.py` | +20…+60, 0 удалений | +38 −0 |
| тестов после | ≥ 89 + 8 + свои | 123: 89 фаз 1–2 + 8 судьи + 26 своих (7 + 19), `pytest -q` зелёный |
| модули | — | `ethsc/cluster.py` 163 строки, импорты `typing`, `ethsc.fingerprint` |

**Что было в красном (первые попытки):**
- `store-read`: проба оркестратора прошла, упал собственный тест исполнителя
  `test_survives_close_and_reopen` (сравнил код не с тем фикстурным байтом). Код
  правильный с первой попытки.
- `cluster.v1` и `cluster.v2`: оба упали на страже `grep -n '_conn'` — в докстринге
  модуля стояла фраза «never touches store._conn». Упоминание взято из блока
  «Contract details» инструкции, который написал оркестратор. **Ошибка автора
  критерия:** страж ловил текст, а не обращение; надо было
  `grep -nE '\._conn\b' | grep -v '^\s*#'` или проверка по `ast`. На `r1` исполнитель
  убрал слово, проба и 19 своих тестов зелёные.
- `cluster-judge`: сломанный `assertIn("eip7702:0xd2e28229", None if … else …)` в
  собственном тесте судьи (`TypeError`), код не при чём; `r1` зелёный, 8/8.

**Опровергаемое утверждение:** первая половина опровергнута — ни одна карта не
прошла с первой попытки, но ни одна из трёх красных не была ошибкой кода
(2 — тесты исполнителей, 1 — страж оркестратора). Правка `store.py` в рамке прошла
по коду с первой попытки. Вторая половина подтверждена: код, прошедший пробу,
прошёл судью (8/8); красный судьи — баг его собственного теста.

**Разведка:** скаут назвал 1 файл (`ethsc/store.py`) — ровно тот существующий файл,
который правился; колода тронула 5, 4 новых файла (`tests/test_store_read.py`,
`ethsc/cluster.py`, `tests/test_cluster.py`, `tests/test_cluster_examples.py`)
добавил оркестратор из Контура и мапы.

**Долг Контура:** `Store.fingerprints()` (все Fingerprint, по `code_id`) и
`Store.code_by_id(code_id)` заданы только этой спекой (§2.2–2.3), в `contour.yaml`
их нет: Function `Build Clusters` говорит «uses: store», но чтения пачкой запись не
называет. Внести в компонент `store` при следующей правке Контура. Туда же уточнения
§2.2: прокси вне L0/L1, члены L1 — адреса всех кодов, самоисключение в
`find_similar`, кортежи `(address, score)`, `score` без округления.

**Сбой Морфа (передать автору):** `map.cards["<id>-judge"]` игнорируется — карта
судьи строится после применения map. Воспроизведение:
`.morph/map_cluster.json` с `"cards": {"cluster-judge": {"context_slice": [..., "ethsc/store.py"]}}`,
`mrph plan --root . --spec contour.yaml --component cluster --map .morph/map_cluster.json --judge`
→ у `cluster-judge` `context_slice` = `["docs/TASK_PHASE3.md", "tests/fixtures/README.md", "ethsc/cluster.py"]`,
без `ethsc/store.py`. Обход: срез судьи дописан руками в `.morph/deck.json` перед
`deck add`. Там же: `plan` отдаёт extra-карту вложенной (`meta`), а сгенерированные —
плоскими; нормализовано руками. Обходы фазы 2 (отфильтрованная мапа на компонент)
применены; `depends_on` на extra-карту внутри одной мапы работает. После рана
checkout остался на `morph/<run-id>` — возвращён на master руками.
