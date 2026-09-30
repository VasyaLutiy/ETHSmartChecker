# Задача для Морфа, фаза 8: флаги риска по байткоду (компоненты `evm`, `cli`, `report`)

Первая веха после пруфа (`plan.md` §6, первый пункт). Два признака опасного
кода видны по runtime-байткоду без исходников; фаза их вычисляет и показывает.

Контур уже правлен под эту фазу (это была первая задача фазы, до спеки):
- `evm`: новая функция **Flag Risk** (`risk_flags`) и объект **Risk Flags**;
- `cli` → **Command Line**: подкоманда `risk`, колонка флагов в `cluster`/`similar`;
- `report` → **Collect Report Data**/**Render Report**: девятая секция `risk`,
  объект **Report Data** расширен.

Все числа ниже посчитаны по `tests/fixtures/codes_26077729.json` 2026-09-30 и
проверены на живом дереве (`ethsc/evm.py` уже умеет `disassemble`/`strip_metadata`/
`detect_proxy`). Регенерация переписывать эти числа не должна — они факт, не гипотеза.

## 1. Зачем это

Система находит копии известного скама (`recheck`, watchlist), но не говорит,
опасен ли **сам** код. Два признака читаются из байткода без источников:
код, способный уничтожить контракт (`SELFDESTRUCT`), и код, отдающий управление
на адрес, который можно поменять (`DELEGATECALL` с адресом из хранилища).
На живом блоке 26077729 это **1 код из 130** с `selfdestruct` и **29 из 130**
(33 адреса из 147) с `mutable_delegatecall` — то есть пятая часть базы отдаёт
управление на изменяемый адрес, и сейчас об этом нигде не сказано.

## 2. Контракт: что должно стать правдой

### 2.1. Формы ВХОДНЫХ данных (что придётся конструировать, и где это определено)

- **`bytes` runtime-кода** — из `.hex`-фикстур: `bytes.fromhex(open(p).read().strip()[2:])`.
  Хелпер `load_hex(name)` уже это делает — **импортировать из `tests/helpers.py`**,
  не писать свой. Синтетический байткод для граничных случаев строится литералом:
  `b"\xff"`, `b"\x60\xff"`, `b""`.
- **Заполненная база** — `block_store()` из `tests/helpers.py` (130 кодов, 147
  адресов с кодом, `counts()` = {addresses 206, addresses_with_code 147,
  addresses_without_code 59, codes 130, blocks 1}). **Импортировать, не строить.**
- **Risk Flags** — dict ровно из двух ключей в фиксированном порядке
  `{"selfdestruct": bool, "mutable_delegatecall": bool}`. Определён в
  `contour.yaml`, компонент `evm`, объект **Risk Flags**.
- **Report Data, секция `risk`** — `{selfdestruct|mutable_delegatecall ->
  {codes:int, code_share:float, addresses:int, address_share:float}}`. Определён в
  `contour.yaml`, `report` → объект **Report Data**.
- **Store**: читать код адреса/кода через существующие `code_of`, `addresses_of`,
  `fingerprints`, `code_by_id` — публичный API `ethsc/store.py`. Схему БД **не трогать**.

### 2.2. Формы ВЫХОДНЫХ данных

- **`risk_flags(code)`** → `{"selfdestruct": bool, "mutable_delegatecall": bool}`.
  `selfdestruct` — опкод `0xFF` есть в `disassemble(strip_metadata(code)[0])`.
  `mutable_delegatecall` — опкод `0xF4` есть в теле, `detect_proxy(code)` не
  `"eip1167"`, и опкод `0x54` (SLOAD) есть в теле. Позиция и порядок опкодов не
  важны, только присутствие. Данных-флоу нет (вне области); это синтаксический
  признак «адрес из хранилища», не доказательство. CFG-достижимости нет: `0xFF`
  за всегда-ложной ветвью тоже считается. Байты `0xFF`/`0xF4`/`0x54` внутри
  PUSH-иммедиата или в metadata-трейлере не считаются (тело — из `strip_metadata`).
  На `b""` и на мусоре не падает, обе — `False`.
- **CLI, колонка флагов** (только `cluster`/`similar`): поле `<flags>` — имена
  истинных флагов в фиксированном порядке `selfdestruct` затем
  `mutable_delegatecall`, через `,`; `-` когда обоих нет (никогда пустое поле).
  `cluster <addr>`: `"<level>\t<key>\t<members>\t<flags>"`, флаги — кода
  **запрошенного** адреса. `similar`: `"<address>\t<score>\t<flags>"`, скор
  остаётся предпоследним полем.
- **`risk` — это ФИЛЬТР, не аннотация.** Печатает `"<address>\t<flags>"` ТОЛЬКО
  для адресов, чей код имеет хотя бы один флаг. Адрес без флагов НЕ печатается
  вовсе — никаких строк с `-`; `-` бывает только в колонке `cluster`/`similar`.
  На базе блока 26077729 (147 адресов с кодом) `risk` печатает **34** строки, не
  147. `--flag NAME` сужает до адресов с этим одним флагом.
- **`report.collect(store)["risk"]`** — см. 2.1. `code_share` по `summary["codes"]`,
  `address_share` по `summary["addresses_with_code"]`; обе `0.0` при нулевом
  знаменателе. Формат JSON, порядок ключей, детерминизм — как у остальных восьми
  секций, править `ethsc/report.py`, не вводить второй сериализации.

### 2.3. Имена

`ethsc/evm.py::risk_flags(code: bytes) -> dict`. Ключи `"selfdestruct"`,
`"mutable_delegatecall"`. CLI-подкоманда `risk`, опция `--flag` со значениями
ровно `selfdestruct`/`mutable_delegatecall`. Секция отчёта `risk`; в ней ключи
`codes`, `code_share`, `addresses`, `address_share`. Опкоды: `SELFDESTRUCT` 0xFF,
`DELEGATECALL` 0xF4, `SLOAD` 0x54.

### 2.4. Что не должно сломаться (byte-for-byte, кроме явно перечисленного)

- **Все 230 существующих тестов** — кроме тех, что закрепляют формат, который
  фаза меняет: `tests/test_cli.py` (последнее поле `similar` — скор,
  `test_cli.py:104`) и `tests/test_report.py` (ровно восемь ключей `collect`,
  `test_report.py:33`). Эти два — цели, их правит соответствующая карта.
- **Форма Fingerprint** — `fingerprints()` возвращает ровно `code_id, size,
  skeleton_hash, selectors, proxy`. Флаги в Fingerprint **не добавлять**
  (`contour.yaml:320`).
- **Схема Code Database** — без новых столбцов; флаги считаются из `code` BLOB.
- **Контракт записей CLI** — tab-separated, все float `"%.4f"`, stdout только
  записи, stderr только сообщения, Secret Hygiene (ключ нигде не печатается).
  Формат `ALERT` (recheck/seed add/backfill/listen) **не меняется** — флаги там
  вне области.
- **Не-сетевые подкоманды** (в т.ч. `risk`) не зовут `infura_url()`, не делают
  rpc-вызовов, работают при снятом `INFURA_API_KEY` (`contour.yaml:909`, `:981`).
- **Восемь прежних секций отчёта** — их числа не меняются; `risk` добавляется
  девятой. `charts.py` не трогать: новой картинки нет (секция — таблица в HTML).

## 3. Приёмка (базовая линия — 230 тестов)

Общие свойства цепочек: `venv/bin/python`; сокеты заблокированы (как в приёмке
фазы 7 — `socket.getaddrinfo/connect/create_connection` бросают); первый шаг —
`ast.parse` файла; узкое → широкое; `-q --tb=line`; смоук-тесты сравнивают
скаляры, не фикстуро-размерные структуры; где сравнение значений неизбежно —
`--tb=short` и `maxDiff = None`. Диагностика первого упавшего звена уходит в
регенерацию, поэтому узкое звено первым.

### 3.1. Область `evm` (флаги)
`ast.parse(ethsc/evm.py)` → импорт `risk_flags` → зонд:
- `risk_flags(code_weth9)` == `{"selfdestruct": False, "mutable_delegatecall": False}`;
- `risk_flags(code_clone_270df012)` — обе `False` (eip1167 исключён, хоть есть 0xF4);
- `risk_flags(b"\xff")["selfdestruct"]` True; `risk_flags(b"\x60\xff")["selfdestruct"]` False;
- `risk_flags(b"")` — обе False, без исключения;
- по `block_store()`: кодов с `selfdestruct` ровно **1** (адрес
  `0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc`), с `mutable_delegatecall` ровно
  **29** (над **33** адресами); пересечения нет.
→ `pytest tests/test_evm.py -q --tb=line` → `pytest tests -q --tb=line`.

### 3.2. Область `cli` (колонка флагов + подкоманда `risk`)
`ast.parse(ethsc/cli.py)` → зонд `main()` на бэкфилл-базе блока 26077729:
- `risk` — 34 строки, первая `0x07696dcab55e62cfef953666b29fe1970518cb00\tmutable_delegatecall`,
  последняя `0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc\tselfdestruct`; два прогона байт-в-байт равны;
- `risk --flag selfdestruct` — ровно одна строка `0xfeeeeee…\tselfdestruct`;
- `risk --flag mutable_delegatecall` — 33 строки;
- `cluster 0x28b5a0e9c621a5badaa536219b3a228c8168cf5d` — одна строка, 4-е поле
  `mutable_delegatecall`, L0 из двух адресов;
- `similar 0xb4e16d0168…` — 4 строки, каждая кончается полем `-`, скор — поле перед ним;
- exit 0, stderr пуст, `INFURA_API_KEY` не нужен, ключ нигде.
→ `pytest tests/test_cli.py tests/test_cli_examples.py -q --tb=line` → `pytest tests -q --tb=line`.

### 3.3. Область `report` (секция `risk`)
`ast.parse(ethsc/report.py)` → зонд:
- `sorted(collect(block_store()).keys())` == девять ключей, включая `risk`;
- `collect(block_store())["risk"]["selfdestruct"]` == `{codes:1, addresses:1,
  code_share: 1/130, address_share: 1/147}` (float точно, не округляя);
- `["risk"]["mutable_delegatecall"]` == `{codes:29, addresses:33,
  code_share: 29/130, address_share: 33/147}`;
- `collect(temp_store())["risk"]` — обе секции `codes 0`, `code_share 0.0`,
  `address_share 0.0`, без исключения;
- два `collect` подряд дают равные структуры; `build_report` пишет байт-в-байт
  одинаковые html/json на двух прогонах; в html нет `<script`/`<link`/`<img`/`http`.
→ `pytest tests/test_report.py tests/test_report_examples.py -q --tb=line` → `pytest tests -q --tb=line`.

### 3.4. Judge-карты `evm-judge`, `cli-judge`, `report-judge`
Пишут только `tests/test_*_examples.py` своей области по примерам Контура
(флаги на реальных фикстурах, `risk`/формат CLI, секция `risk` отчёта).
Приёмка каждой — её файл примеров плюс полный прогон. Смоук в собственном
`test_*.py` карты-кода — максимум пять функций, без Fake*-классов (стабы из
`tests/helpers.py`), офлайн.

## 4. Ограничения

1. Конверт правки существующего файла 20–60 строк; не влезло — делить карту, не
   расширять слайс. `risk_flags` — чистая логика, лучше отдельным блоком в `evm.py`.
2. Карта аддитивна; удаления — красный флаг (кроме двух закреплённых правок
   формата в `test_cli.py`/`test_report.py`).
3. Код и его тест — одна карта через `targets`.
4. Один файл — один владелец на поколение.
5. `tests/helpers.py` — общий, в слайсе каждой карты, что пишет тесты; стабы
   импортировать, не плодить. Правок хелперов эта фаза не планирует.
6. Правка одного файла не влияет на текущий прогон (модуль уже в памяти) — потому
   `cli`/`report` зависят от `evm` по поколению, не по правке.

## 5–6. Техники и что намеренно не указано

Идиому карты брать из принятого прогона (`.morph/runs/*/deck.json`). Разбивка на
карты, их число, границы, слайсы, порядок, поколения и точные формулировки
приёмки — работа оркестратора (Фаза 4), в спеке их нет.

## 7. Вне области

mint и blacklist только для владельца · изменяемые комиссии · **анализ потоков
данных** (потому `mutable_delegatecall` — синтаксический признак, не доказательство)
· сверка с Etherscan и Sourcify · флаги в алертах watchlist · CFG-достижимость
`SELFDESTRUCT` · изменение схемы БД · изменение формы Fingerprint · новая
matplotlib-картинка риска · новые фикстуры (реальный якорь `selfdestruct` — один
код из 130, плюс синтетические байты).

## 8. Как запускать

```bash
cd /home/john/Documents/Work2026/ETHSmartChecker
set -a; source /home/john/Documents/Work2026/MorphProject/morph-lab/.env; set +a
~/Documents/python_venv/venv_mrph/bin/mrph run --processor glm
```
Дерево чистое до старта. Тесты и приёмка — проектный `venv/bin/python`.

## 9. Пререгистрация предсказаний

| величина | предсказание |
|---|---|
| карт в колоде | 6 (evm, evm-judge, cli, cli-judge, report, report-judge) |
| поколений | 2 (evm+judge → cli/report+judge) |
| счёт исполнителя | ≈ $0.06–0.10 |
| счёт сессии оркестратора | ≈ $0.10–0.15 |
| карт с регенерацией | ≤ 2 |
| write-write конфликтов на preflight | 0 |
| тестов | > 230 |

**Опровержимое утверждение:** после прогона `venv/bin/python -m ethsc --db <база
блока 26077729> risk` печатает **ровно 34 строки**, первая с
`0x07696dcab55e62cfef953666b29fe1970518cb00`, последняя с
`0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc`.

## 10. Что записать в конце

`/cost` сессии, счёт провайдера, время очереди на поколение, число регенераций,
итоговое число тестов и **доллары на принятую карту**. Отдельной строкой —
разведка: сколько файлов назвал скаут / сколько тронула колода / что добавил
оркестратор и почему; минуты и `stop_reason` скаута; его счёт отдельно от
исполнителей.

## 11. Факт прогона

`<заполняется после прогона: таблица предсказание/факт, включая промахи.>`
