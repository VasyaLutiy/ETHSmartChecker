# Задача для Морфа, фаза 6, задача 1 из 2: компонент `cli`, две правки по живому смоуку

> Дата: 29.09.2026. Проект ETHSmartChecker. Запись системы — `contour.yaml`, группа `cli`,
> Function `Command Line` (контракт обеих правок внесён коммитом `a07efa9`: абзац про
> `KeyboardInterrupt`, строка `stopped: …` для кода 3, два новых примера про Ctrl-C).
> Источник — `docs/TASK_PHASE5.md` §13, факт смоука. Где Контур не уточняет форму вывода,
> уточняет §2.2 этого файла. Фикстуры — `tests/fixtures/`, новых нет. **Сеть не нужна и
> запрещена** в тестах и приёмках: `rpc` и `sleep` инъецируются в `main()`. Разбивки на карты
> здесь нет — она в `morph-map.json`.

## 1. Зачем это

Смоук фазы 5 (стенд Hetzner, 28–29.09, 1 ч 50 мин `listen`, 333 блока, 4419 кодов) прошёл
четыре проверки пруфа из пяти, но нашёл два дефекта `cli`, оба видны только в живой работе:

- **Ctrl-C внутри прохода — трейсбек.** `KeyboardInterrupt` перехватывается только вокруг
  `sleep(interval)` (`ethsc/cli.py:104–107`). Проход `follow_chain` занимает секунды–минуты
  (≈ 7 тыс. кредитов, ~90 `eth_getCode` на блок), пауза — 12 с, так что Ctrl-C чаще
  приходится на проход. В смоуке из двух проверочных прерываний одно попало в backoff-сон
  клиента (`ethsc/rpc.py:101`) и дало трейсбек и выход по сигналу, код −2 вместо 0.
  Прогресс сохранился (он пишется только после полного блока), так что потери данных нет —
  есть нарушение контракта «без трейсбека» и код, по которому скрипт-обёртка не отличит
  остановку от падения. В `backfill` перехвата нет вовсе.
- **Остановка по бюджету молчит.** Два из трёх запусков `listen` под `nohup` закончились
  бюджетом (`--daily-budget 1000000`, затем 2 000 000; ledger 1 999 800 за 28.09): код 3 и
  ни одной строки ни в stdout, ни в stderr. В логе `nohup` это неотличимо от падения;
  чтобы понять, что случилось, пришлось открывать базу и считать ledger руками.

176 тестов зелёные (`venv/bin/python -m pytest tests -q`, 29.09, 69 с). Один из них
закрепляет старое поведение: `tests/test_cli_examples.py:213` требует пустой stderr при
коде 3 — по новому контракту он красный и переписывается в этой задаче.

## 2. Контракт

### 2.1. Формы ВХОДНЫХ данных (что придётся конструировать, и где это определено)

- `summary` — результат `follow_chain(...)`, `ethsc/ingest.py:171–230`:
  `{"blocks": int, "stopped": None | "budget" | "cap", "progress": int | None, "alerts":
  list}`. `progress` — `store.get_progress()` после прохода; `None`, если в базе прогресса
  ещё нет (свежая база, `backfill` остановлен до первого полного блока). Поля «потрачено» в
  `summary` нет.
- `day` — строка `"%Y-%m-%d"` по UTC; `follow_chain` принимает `day=` и при `None` сам
  берёт сегодняшнюю дату (`ethsc/ingest.py:161–164`). Контур: `listen` обновляет день на
  каждом проходе.
- `store.spent(day) -> int` — сумма кредитов за день из ledger (`ethsc/store.py:228`).
- `PRICES` — `ethsc/config.py:6` (`eth_blockNumber` 80, `eth_getBlockReceipts` 1000,
  `eth_getCode` 80).
- Источники `KeyboardInterrupt` в проходе: `rpc.call(...)` (транспорт и backoff-сон
  `RpcClient`, `ethsc/rpc.py`), вызов `get_code` внутри `ingest_block` (его `except
  Exception` на `ethsc/ingest.py:102` `KeyboardInterrupt` не ловит — это `BaseException`),
  записи в `Store`, `sleep(interval)`.
- Тестовые стабы — только `tests/helpers.py` (`FakeRpc`, `temp_store`, `block_codes`,
  `block_receipts`, `load_hex`; `tests/helpers.py:91–129`). `FakeRpc(codes=…)` отвечает на
  `eth_getCode` выражением `codes[params[0]]`, поэтому `KeyboardInterrupt` на первом
  `eth_getCode` строится подклассом `dict`, чей `__getitem__` его поднимает;
  `FakeRpc(fail=KeyboardInterrupt())` поднимает его на любом вызове, включая
  `eth_blockNumber`. `tests/helpers.py` в этой задаче не меняется.

### 2.2. Формы ВЫХОДНЫХ данных

**Строка остановки (код 3).** Когда проход `backfill` или `listen` завершён с
`summary["stopped"]` не `None`, `main` возвращает 3 и печатает в stderr ровно одну строку:

```
stopped: <stopped>, spent <N> credits, progress <P>
```

- `<stopped>` — `summary["stopped"]` как есть: `budget` или `cap`;
- `<N>` — `store.spent(day)` целым числом, где `day` — тот же день, с которым был вызван
  этот `follow_chain` (CLI вычисляет день сам и передаёт его `day=`; на каждом проходе
  `listen` заново);
- `<P>` — `summary["progress"]` десятичным числом, или слово `none`, если он `None`;
- разделители — ровно `", "`, строка кончается `\n`, других строк в stderr нет. Алерты
  этого прохода печатаются в stdout как раньше, до строки остановки.

Примеры (фикстуры блока 26077729, `PRICES`):

| вызов | код | stderr |
|---|---|---|
| свежая база, `backfill --from 26077729 --to 26077729 --daily-budget 79` | 3 | `stopped: budget, spent 0 credits, progress none` |
| прогресс 26077728, `backfill --from 26077729 --to 26077729 --daily-budget 10000` | 3 | `stopped: budget, spent 9960 credits, progress 26077728` |
| свежая база, `backfill --from 26077729 --to 26077729 --max-calls-per-block 5` | 3 | `stopped: cap, spent 1480 credits, progress none` |
| прогресс 26077728, `listen --daily-budget 10000` | 3, `sleep` не вызван | `stopped: budget, spent 9960 credits, progress 26077728` |

**Чистая остановка по Ctrl-C.** `KeyboardInterrupt` где угодно внутри `listen` или
`backfill` — в `sleep`, в `rpc.call`, в `ingest_block`, в записи в `Store` — даёт: `main`
возвращает 0; ни одной строки `Traceback` ни в stdout, ни в stderr; stderr пуст (новой
строки для Ctrl-C нет); прогресс в базе — последний полный блок; `store.close()` выполнен.
Алерты блоков, завершённых в прерванном проходе, не печатаются (§7). `backfill`, прерванный
посреди диапазона, тоже возвращает 0.

Всё остальное — без изменений: код 0 при `stopped is None`, код 1 при `RpcError` (stderr —
`str(err)`), код 2 при ошибке использования, формат строк `ALERT` и прочих подкоманд.

### 2.3. Имена

- Публичное: `ethsc.cli.main(argv=None, rpc=None, sleep=None) -> int` — сигнатура та же.
- Литералы вывода: `stopped: `, `, spent `, ` credits, progress `, `none`.
- Значения `stopped`: `budget`, `cap` (из `ethsc/ingest.py`, не переименовывать).
- `follow_chain(..., day=<str>)` — имя параметра `day`.
- Внутренние хелперы `ethsc/cli.py` (`_follow`, `_run_listen`, `_run_backfill`) можно
  менять; новые — на усмотрение исполнителя.

### 2.4. Что не должно сломаться

- 175 из 176 существующих тестов — без правки; `tests/test_cli.py::…::test_listen_interrupt`
  (Ctrl-C в `sleep` → 0, `sleep` вызван один раз с 12, прогресс 26077729) — тоже.
- Единственный тест, который меняется, — `test_backfill_budget_stop_exit_code_3_empty_stdout`
  в `tests/test_cli_examples.py`: stdout по-прежнему пуст, stderr теперь ровно одна строка
  `stopped: budget, …`.
- Коды 0/1/2 и форматы stdout всех подкоманд.

## 3. Приёмка

Базовая линия: 176 тестов. `pytest` идёт через обёртку фаз 4–5, подменяющую
`socket.getaddrinfo`/`socket.socket.connect`/`socket.create_connection` на
`OSError("network blocked")`, с `INFURA_API_KEY=TESTKEY-ENV-0000` в окружении. Везде
`-q --tb=line`.

1. **Кодовая карта `cli`** (`ethsc/cli.py`, `tests/test_cli.py`):
   1. `ast.parse(..., feature_version=(3,9))` по обоим файлам;
   2. стражи по `ast` (не по тексту): `ethsc/cli.py` не импортирует `urllib`, `http`,
      `socket`, `sqlite3`; в `ethsc/cli.py` нет `Attribute` с именем, начинающимся на `_`,
      у объекта `store`/`Store` (приватные поля `Store`); в `ethsc/cli.py` каждый
      `ExceptHandler` имеет тип (нет голого `except:`), и ни один не называет
      `BaseException`; `tests/test_cli.py` — не больше 6 функций `test_*`, импортирует из
      `tests.helpers`, не определяет класс `FakeRpc`/`FakeTransport`;
   3. **проба оркестратора** (сеть заблокирована, `TESTKEY-0000` в окружении, stdout и stderr
      каждого вызова `main` перехвачены, `sleep` — записывающий фейк):
      - четыре строки таблицы §2.2 — код и stderr **точно**, stdout пуст; для `listen` —
        `sleep` не вызван;
      - `listen`, прогресс 26077728, `FakeRpc(codes=<dict, поднимающий KeyboardInterrupt на
        первом чтении>)` → код 0, stdout и stderr пусты, прогресс 26077728, `sleep` не вызван;
      - то же для `backfill --from 26077729 --to 26077729` → код 0, прогресс 26077728;
      - `listen` с `FakeRpc(fail=KeyboardInterrupt())` → код 0, stderr пуст;
      - `listen`, прогресс 26077728, `sleep` возвращается нормально, а `rpc` поднимает
        `KeyboardInterrupt` на втором `eth_blockNumber` (второй проход) → код 0, `sleep`
        вызван ровно один раз с 12, прогресс 26077729;
      - регрессия: `listen` с `FakeRpc(fail=RpcError(None, "transport failed"))` → код 1,
        stderr одна строка, без `Traceback` и без `TESTKEY-0000`; `listen` с `sleep`,
        поднимающим `KeyboardInterrupt` → код 0, `sleep == [12]`, прогресс 26077729;
        `backfill` без бюджета на свежей базе → код 0, stderr пуст;
      печатает `<сценарий>: got …, want …` по каждому расхождению;
   4. `pytest tests/test_cli.py -q --tb=line`;
   5. `pytest tests -q --tb=line --deselect
      tests/test_cli_examples.py::CliExamplesTest::test_backfill_budget_stop_exit_code_3_empty_stdout`
      — тест, закрепляющий старое поведение, переписывает карта-судья (у неё он не
      исключается);
   6. страж Secret Hygiene: настоящий ключ из `.env` не встречается ни в `ethsc/*.py`,
      `tests/*.py`, ни в выводе приёмки; вывод печатается с заменой ключа на `<KEY>`.
2. **Карта судьи** (`tests/test_cli_examples.py`, код не трогает):
   1. `ast.parse`; страж по `ast`: импорт стабов из `tests.helpers`, свой `FakeRpc`/
      `FakeTransport` не определён; функций `test_*` не меньше 9 (7 было + 2 новых примера
      Контура про Ctrl-C);
   2. `pytest tests/test_cli_examples.py -q --tb=line`;
   3. **мутационная проверка**: копия дерева во временный каталог, где `ethsc/cli.py`
      заменён на версию `f49f949` (до правок) — `pytest tests/test_cli_examples.py` на ней
      **падает** не меньше чем 2 тестами (строка остановки и Ctrl-C внутри прохода);
   4. `pytest tests -q --tb=line` — без исключений, все зелёные;
   5. страж Secret Hygiene, как у карты 1.
3. **Проза, после рана**: число тестов ≥ 178, `git diff f49f949 -- ethsc/` трогает только
   `ethsc/cli.py`.

## 4. Ограничения

- Python 3.12 в рантайме, синтаксис совместим с 3.9, только стандартная библиотека.
- Правятся существующие файлы: `ethsc/cli.py` (конверт правки ~20–50 строк),
  `tests/test_cli.py` (не больше одного нового `test_*`, пять старых без изменений),
  `tests/test_cli_examples.py` (правка одного теста и новые тесты по примерам Контура).
  Остальные файлы, включая `ethsc/ingest.py`, `ethsc/rpc.py`, `ethsc/store.py`,
  `tests/helpers.py`, `contour.yaml`, фикстуры — не трогаются.
- Один файл — одна карта-владелец: `ethsc/cli.py` и `tests/test_cli.py` — карта `cli`;
  `tests/test_cli_examples.py` — карта-судья. Судья читает `ethsc/cli.py`, поэтому идёт
  после `cli`.
- `KeyboardInterrupt` ловится по имени; голый `except:` и `except BaseException` запрещены
  — они проглотили бы и `SystemExit`.
- No Network In Core, Secret Hygiene — как в фазе 5.
- Правка, сделанная во время рана, на ран не влияет (модули уже в памяти); дерево во время
  рана не трогается — правка файла из среза даёт `stale-context`.

## 5–6. Техники; что не указано

Как в `TASK_TEMPLATE`. Не указано: где именно в `ethsc/cli.py` стоит перехват
(`_follow`, `_run_listen`/`_run_backfill` или `main`) — лишь бы покрывал весь проход и
паузу и выполнял `store.close()`; как вычисляется UTC-дата (любой способ, дающий
`"%Y-%m-%d"` как `ethsc/ingest.py:162`). Реальный сигнал SIGINT в подпроцессе не
проверяется в приёмке (в подпроцесс не инъецировать `rpc`) — это живой смоук Джона.

## 7. Вне области

- **Алерты блоков, завершённых в прерванном проходе, теряются.** `follow_chain` отдаёт
  `alerts` только в конце прохода (`ethsc/ingest.py:222,229`); при Ctrl-C посреди прохода
  блоки до прерывания записаны и прогресс сдвинут, но их `ALERT` так и не печатаются, а при
  перезапуске адреса уже известны и пропускаются — алерт потерян навсегда. Исправление —
  задача 2 фазы 6 (компонент `ingest`, с правкой Контура `Follow Chain`), не здесь.
- Пересчёт `day` на каждый блок внутри `follow_chain` (долг Контура 3 из §13 фазы 5) —
  задача 2 или позже.
- Отличимость прерванного `backfill` от завершённого по коду выхода (оба 0 по Контуру).
- Строка в stderr при Ctrl-C; обработка SIGTERM; демон, systemd, автоперезапуск.
- Скорость `similar` (MinHash/LSH), опровергнутое предсказание §9 фазы 5.
- Правка `ethsc/ingest.py`, `rpc.py`, `store.py`, `config.py`, `tests/helpers.py`,
  `contour.yaml`, фикстур.

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
| карт в колоде | 2 (`cli` — `variants: 2`, `cli-judge`) |
| поколений | 2 (`cli` → `cli-judge`) |
| счёт исполнителя | $0.02–0.10 |
| карт с регенерацией | 0–1 |
| тестов после | 178–184 |

**Опровергаемое утверждение:** обе карты проходят не позже `r1`; если `cli` сгорит, то на
пробе Ctrl-C во втором проходе `listen` (перехват только вокруг одного `_follow`, а не всего
цикла) или на `progress none`.

## 10. Что записать в конце

Принято/сожжено карт, регенерации (что было в красном), минуты на поколение, счёт
провайдера, итоговое число тестов, имя ветки `morph/<run-id>`, строка разведки (сколько
файлов назвал скаут / сколько тронула колода / что добавлено руками и почему, минуты и
`stop_reason` скаута, его счёт отдельно).
