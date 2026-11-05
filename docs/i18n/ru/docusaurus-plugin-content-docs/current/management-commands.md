---
title: Команды управления
sidebar_position: 8
---

Django-RMQ поставляется с тремя командами управления. `setup_rabbitmq_topology` и `start_consumers` расширяют
`RDDBaseCommand`; `check_rabbitmq_connections` — это лёгкий healthcheck, который намеренно его не расширяет.

## `setup_rabbitmq_topology`

Объявляет все обмены, очереди и привязки, зарегистрированные в [SetupRegistry](./registries.md), для каждого алиаса
подключения. Операция идемпотентна и безопасна для выполнения при каждом деплое.

```bash
uv run python manage.py setup_rabbitmq_topology
```

### Параметры

| Параметр  | Тип   | По умолчанию | Описание                                                                                                                              |
|-----------|-------|--------------|---------------------------------------------------------------------------------------------------------------------------------------|
| `--using` | `str` | `None`       | Алиас подключения из `RABBITMQ_CONNECTIONS` для настройки. Если не указан, настройка выполняется для всех сконфигурированных алиасов. |

### Что делает команда

Для каждого алиаса команда:

1. Открывает producer-соединение и создаёт канал.
2. Оборачивает канал в `RecordingChannel` — прозрачный прокси, перехватывающий вызовы `exchange_declare`,
   `queue_declare` и `queue_bind` для записи объявленных объектов.
3. Вызывает `SetupRegistry.run_all(channel)`, выполняя все зарегистрированные `SetupFn` в порядке их регистрации.
4. Закрывает канал.
5. Выводит отчёт о топологии — обмены, очереди и привязки, объявленные в ходе выполнения (без повторов по имени).

### Пример вывода

```
RabbitMQ setup complete for alias 'default'
  Exchanges (1):
    - orders [direct]
  Queues (2):
    - orders
    - orders.dlx {'x-dead-letter-exchange': 'dlx'}
  Bindings (1):
    - orders --[orders]--> orders
```

### Пример: запуск для конкретного алиаса

```bash
uv run python manage.py setup_rabbitmq_topology --using analytics
```

### Идемпотентность

Объявления топологии RabbitMQ (exchange/queue declare, queue bind) являются passive-safe, если аргументы совпадают с
существующей сущностью. Повторный запуск команды на одном и том же брокере не вызывает ошибок и не изменяет уже
объявленную топологию. Это позволяет безопасно включить её в пайплайны деплоя.

Интеграционный тест, подтверждающий это поведение:

```python
from django.core.management import call_command
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType

from django_rmq.registries.setup_registry import get_setup_registry


def setup(channel: BlockingChannel) -> None:
    channel.exchange_declare(exchange='orders', exchange_type=ExchangeType.direct, durable=True)
    channel.queue_declare(queue='orders', durable=True)
    channel.queue_bind(queue='orders', exchange='orders', routing_key='rk')


get_setup_registry().register(fn=setup)

call_command('setup_rabbitmq_topology')

# Second call must not raise.
call_command('setup_rabbitmq_topology')
```

## `start_consumers`

Запускает всех потребителей, зарегистрированных в [ConsumersRegistry](./registries.md). Каждый потребитель
выполняется в собственном потоке. Команда блокируется до получения сигнала `SIGTERM` или `SIGINT`, после чего ожидает
завершения всех потоков перед выходом.

```bash
uv run python manage.py start_consumers
```

### Параметры

| Параметр  | Тип   | По умолчанию | Описание                                                                                                                              |
|-----------|-------|--------------|---------------------------------------------------------------------------------------------------------------------------------------|
| `--using` | `str` | `None`       | Алиас подключения из `RABBITMQ_CONNECTIONS` для запуска. Если не указан, потребители запускаются для всех сконфигурированных алиасов. |

### Что делает команда

1. Определяет список алиасов (`--using` выбирает один; в противном случае — все сконфигурированные алиасы).
2. Собирает всех потребителей, зарегистрированных для этих алиасов, через `ConsumersRegistry.all()`.
3. Выводит таблицу потребителей, сгруппированных по алиасу, с именем очереди, значением prefetch count и именем
   обработчика.
4. Устанавливает обработчики `SIGTERM` и `SIGINT`, которые устанавливают общий `threading.Event`.
5. Создаёт по одному `threading.Thread` на каждого потребителя, каждый из которых вызывает
   `consumer.consume(stop_event=stop_event)`.
6. Выполняет join для всех потоков — блокируется до завершения каждого из них.

Если ни одного потребителя не зарегистрировано, команда записывает предупреждение в лог и немедленно завершается без
блокировки.

### Таблица потребителей

Перед запуском потоков команда выводит сводную информацию:

```
Consumers
Alias: default
  ├─ queue=orders  prefetch_count=5  handler=handle_order — Is consuming...
  └─ queue=notifications  prefetch_count=1  handler=handle_notification — Is consuming...
```

### Корректное завершение работы

Отправьте `SIGTERM` (или нажмите `Ctrl-C` для `SIGINT`), чтобы инициировать завершение. Обработчик сигнала устанавливает
общий stop-событие; каждый поток потребителя выходит из цикла `basic_consume` при его обнаружении. Команда ожидает
завершения всех потоков перед возвратом.

```bash
# In another terminal or from an orchestrator:
kill -TERM <pid>
```

### Пример: запуск для конкретного алиаса

```bash
uv run python manage.py start_consumers --using analytics
```

## `check_rabbitmq_connections`

Команда-хелсчек, проверяющая доступность RabbitMQ. Каждый узел каждого алиаса проверяется параллельно: команда
открывает соединение и сразу же закрывает его, используя короткие таймауты из
`RABBITMQ_HEALTHCHECK`. Алиас считается доступным, если ответил хотя бы один
его узел. Команда завершается по собственному дедлайну (по умолчанию 15 секунд) и печатает результат, даже если часть
узлов не отвечает. Предназначена для readiness/liveness-хелсчеков: каждое событие печатается отдельной строкой и сразу
сбрасывается в stdout; завершается с кодом `0`, если все алиасы доступны, и с кодом `1`, если хотя бы один недоступен.
Как по выводу понять, на что ушло время, описано в разделе
Диагностика таймаутов хелсчека.

```bash
uv run python manage.py check_rabbitmq_connections
```

### Параметры

| Параметр        | Тип              | По умолчанию                                | Описание                                                                                                                                                                                         |
|-----------------|------------------|---------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--using`       | `str`            | `None`                                      | Алиас подключения из `RABBITMQ_CONNECTIONS` для проверки. Если не указан, проверяются все сконфигурированные алиасы.                                                                             |
| `--format`      | `json` \| `text` | `text`                                      | Формат вывода: текст `key=value` в стиле logfmt или один JSON-объект на строку (JSON Lines).                                                                                                     |
| `--timeout`     | `float`          | `RABBITMQ_HEALTHCHECK['DEADLINE']` (`15.0`) | Общий дедлайн в секундах на всю проверку (все алиасы). Должен быть больше 0, иначе `CommandError`. По истечении алиасы, у которых не нашлось живого узла, получают статус `fail` с `TimeoutError`. |
| `--skip-checks` | флаг             | выкл.                                       | Ничего не делает, оставлен для обратной совместимости: команда никогда не запускает системные проверки Django, поэтому флаг ни на что не влияет.                                                 |

При вызове из кода (`call_command`) опция `--format` передаётся как `output_format`, а `--timeout` — как `timeout`.
Параметры `--no-color` и `--force-color` ни на что не влияют: вывод никогда не бывает цветным. Системные проверки Django
эта команда не запускает — ни из командной строки, ни через `call_command`.

### Что делает команда

1. Не запускает системные проверки Django (`requires_system_checks = ()`): проба стартует каждые несколько секунд в
   новом процессе, и проверки (в том числе импорт всего URLconf) оплачивались бы при каждом запуске.
2. Проверяет, что django_rmq инициализирован — вызывает `ImproperlyConfigured`, если `django_rmq` отсутствует в
   `INSTALLED_APPS` (в этом случае ничего не выводится).
3. Проверяет `--timeout`: значение `<= 0` вызывает `CommandError` (до того, как что-либо напечатано). Дедлайн —
   это `--timeout` или, если он не указан, `DEADLINE` из `RABBITMQ_HEALTHCHECK`.
4. Определяет список алиасов (`--using` выбирает один; в противном случае — все сконфигурированные алиасы).
5. Выводит событие `startup`.
6. Для каждого алиаса строит параметры подключения к каждому узлу через
   `RabbitMQConnectionManager.build_probe_parameters(socket_timeout=…, stack_timeout=…)` с таймаутами из
   `RABBITMQ_HEALTHCHECK`. Неизвестный алиас вызывает `ImproperlyConfigured` именно здесь — после `startup`, но до
   запуска потоков.
7. Запускает сразу по одному daemon-потоку на каждый узел всех алиасов. Каждый поток открывает соединение только к
   своему узлу и закрывает его. Любое исключение считается отказом узла.
8. Выводит события `check` по мере того, как алиасы получают вердикт:
    - алиас `ok` — как только успешно ответил первый узел;
    - алиас `fail` — когда отказали все его узлы;
    - когда истекает дедлайн, все ещё не определившиеся алиасы получают `fail` с ошибкой `TimeoutError`.
9. Выводит итоговое событие `summary`; в текстовом формате после него — строки `ERROR`.
10. Если хотя бы один алиас недоступен, завершается с ошибкой — см. Коды выхода. Потоки проб — daemon,
    поэтому они не удерживают процесс: зависшие узлы не задерживают выход.

Собственные `SOCKET_TIMEOUT` / `STACK_TIMEOUT` алиаса и `SHUFFLE_NODES` команда не использует: время пробы не должно
зависеть от порядка узлов и от таймаутов, подобранных для рабочих соединений. Подробнее о том, во что обходится
недоступный узел, — в разделе Таймауты узлов и время failover.

### События вывода

| Событие   | Когда                                                                                  | Поля JSON                                                                                         | Текстовый вид                                                                   |
|-----------|----------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| `startup` | Один раз, до открытия любого соединения                                                | `seconds` (число или `null`)                                                                      | `startup=8.71s` / `startup=unknown`                                             |
| `check`   | Один раз для каждого алиаса, в порядке завершения проверки (не в порядке конфигурации) | `status` (`ok`/`fail`), `alias`, `seconds`, `node` (только при `ok`), `error` (только при `fail`) | `OK alias=… node=… connect=…` / `FAIL alias=… took=…` + `ERROR alias=… error=…` |
| `summary` | Один раз, после всех событий `check`                                                   | `status` (`healthy`/`unhealthy`), `healthy`, `total`, `failed` (список), `seconds`                | `HEALTHY aliases=2/2 total=…` / `UNHEALTHY failed=… aliases=1/2 total=…`        |

Пояснения к полям:

- `startup.seconds` — время от старта процесса Python до начала проверки: интерпретатор, импорты, `django.setup()`.
- `node` — `host:port` узла, который ответил первым.
- `error` — строка из ошибок отказавших узлов: каждая в виде `<host>:<port> <ExceptionType>: <message>`, через `; `, в
  порядке отказов. Если сообщение исключения пустое, берётся `repr(exc.args)`, а при отсутствии аргументов — только имя
  типа (например, `rmq-1:5672 AMQPConnectionError`). Пробельные символы схлопываются. Если истёк дедлайн, строка
  начинается с `TimeoutError: no node answered within <deadline>s`, затем идут ошибки отказавших узлов, а в конце —
  узлы без ответа в виде `<host>:<port> no answer` в порядке `NODES`.
- `seconds` в событии `check` (в тексте `connect` / `took`) — время от начала фазы проверки (все пробы стартуют
  одновременно): для `ok` — до момента, когда первый успешный узел завершил подключение и закрытие, для `fail` — до
  отказа последнего узла либо около значения дедлайна.
- `seconds` в событии `summary` (в тексте `total`) — `startup` плюс фактическая длительность фазы проверки (алиасы
  проверяются параллельно, поэтому это примерно время самого медленного алиаса, не больше дедлайна), а не сумма
  длительностей алиасов.

### Пример вывода

Значения времени и текст ошибки в примерах иллюстративные.

JSON (`--format json`), успех:

```
{"event": "startup", "seconds": 8.712}
{"event": "check", "status": "ok", "alias": "default", "seconds": 0.142, "node": "rmq-2:5672"}
{"event": "check", "status": "ok", "alias": "analytics", "seconds": 0.018, "node": "rmq-1:5672"}
{"event": "summary", "status": "healthy", "healthy": 2, "total": 2, "failed": [], "seconds": 8.874}
```

JSON, ошибка:

```
{"event": "startup", "seconds": 1.204}
{"event": "check", "status": "ok", "alias": "default", "seconds": 0.021, "node": "rmq-2:5672"}
{"event": "check", "status": "fail", "alias": "analytics", "seconds": 0.048, "error": "rmq-1:5672 AMQPConnectionError: (AMQPConnectorSocketConnectError: ConnectionRefusedError(111, 'Connection refused'),); rmq-2:5672 AMQPConnectionError: (AMQPConnectorSocketConnectError: ConnectionRefusedError(111, 'Connection refused'),)"}
{"event": "summary", "status": "unhealthy", "healthy": 1, "total": 2, "failed": ["analytics"], "seconds": 1.273}
```

Текст (по умолчанию), успешный хелсчек:

```
startup=8.71s
OK alias=default node=rmq-2:5672 connect=0.14s
OK alias=analytics node=rmq-1:5672 connect=0.02s
HEALTHY aliases=2/2 total=8.87s
```

Текст, ошибка:

```
startup=1.20s
OK alias=default node=rmq-2:5672 connect=0.02s
FAIL alias=analytics took=0.05s
UNHEALTHY failed=analytics aliases=1/2 total=1.27s
ERROR alias=analytics error="rmq-1:5672 AMQPConnectionError: (AMQPConnectorSocketConnectError: ConnectionRefusedError(111, 'Connection refused'),); rmq-2:5672 AMQPConnectionError: (AMQPConnectorSocketConnectError: ConnectionRefusedError(111, 'Connection refused'),)"
```

Текст, истёк дедлайн (алиас `analytics` не получил ответа ни от одного узла за 15 секунд):

```
startup=1.20s
OK alias=default node=rmq-2:5672 connect=0.02s
FAIL alias=analytics took=15.00s
UNHEALTHY failed=analytics aliases=1/2 total=16.22s
ERROR alias=analytics error="TimeoutError: no node answered within 15s; rmq-1:5672 AMQPConnectionError: (AMQPConnectorSocketConnectError: ConnectionRefusedError(111, 'Connection refused'),); rmq-2:5672 no answer"
```

Текст, недоступный первый узел не задерживает вердикт (первый узел в `NODES` — «чёрная дыра», пакеты отбрасываются;
алиас получает `OK` по второму узлу):

```
startup=1.20s
OK alias=default node=localhost:5672 connect=0.01s
HEALTHY aliases=1/1 total=1.22s
```

Для неудачного исхода строка `CommandError: ...` не печатается. Исключение — некорректный `--timeout`: такая строка
выводится в stderr, процесс завершается с кодом 1. В текстовом формате значение берётся в двойные кавычки, если оно
пустое или содержит пробел, `"`, `=`, `\`, табуляцию или перевод строки; внутри кавычек `\` записывается как `\\`, а
`"` — как `\"`. Например:

```
ERROR alias=default error="OSError: connection \"refused\""
```

В текстовом формате список `failed` в строке `UNHEALTHY` перечисляет алиасы через запятую без пробелов и стоит перед
`aliases=`.

Текстовый вывод начинается с самого важного, чтобы оно сохранилось, если вывод пробы обрезается (например, из-за
ограничения длины сохраняемого вывода хелсчека): строки `FAIL` короткие и не содержат текста ошибки, а сами ошибки —
они бывают длинными — печатаются после `summary` строками `ERROR`, по одной на каждый упавший алиас, в том же порядке,
что и строки `check` (порядок завершения). В JSON ошибка остаётся в событии `check`, а `summary` — последняя строка.

JSON удобен для агрегаторов логов, текст — для чтения человеком (например, в выводе `docker inspect`).

### Пример: проверка конкретного алиаса

```bash
uv run python manage.py check_rabbitmq_connections --using analytics
uv run python manage.py check_rabbitmq_connections --using analytics --format json
uv run python manage.py check_rabbitmq_connections --timeout 5
```

### Вызов из кода

```python
from django.core.management import call_command
from django.core.management.base import CommandError

try:
    call_command('check_rabbitmq_connections', using='analytics', output_format='text', timeout=5.0)
except CommandError as exc:
    print(exc)  # unhealthy: analytics
```

При вызове через `call_command` формат передаётся как `output_format` (не `format`), а дедлайн — как `timeout`. Если
`timeout <= 0`, команда вызывает `CommandError('--timeout must be a positive number of seconds, got …')`. Если хотя бы
один алиас недоступен, команда вызывает `CommandError('unhealthy: <alias1>, <alias2>')` со списком только недоступных
алиасов. События при этом всё равно печатаются в stdout команды.

### Коды выхода

| Код | Значение                                                                                                                                                                                                                 |
|-----|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `0` | Все проверенные алиасы доступны (`summary.status` равен `healthy`).                                                                                                                                                      |
| `1` | Хотя бы один алиас недоступен (`summary.status` равен `unhealthy`). Из командной строки процесс завершается с кодом 1 без строки `CommandError`; через `call_command` вызывается `CommandError('unhealthy: <aliases>')`. |

Если django_rmq не инициализирован или в `--using` указан неизвестный алиас, возникает `ImproperlyConfigured`:
процесс завершается с ненулевым кодом и трейсбеком, а `summary` не печатается. При неизвестном алиасе строка `startup`
к этому моменту уже может быть напечатана.

Некорректный `--timeout` обрабатывается так:

- значение `<= 0` — `CommandError: --timeout must be a positive number of seconds, got …` в stderr, код выхода `1`
  (ничего из событий не печатается);
- нечисловое значение — ошибка argparse (usage), код выхода `2`.

### Логирование

Логгер `rabbitmq`, `source` — `check_rabbitmq_connections`. Логи не смешиваются с выводом команды и обрабатываются
согласно настройке `LOGGING` вашего проекта.

| Исход            | Уровень   | `message`                    | `data`                              |
|------------------|-----------|------------------------------|-------------------------------------|
| Узел ответил     | `debug`   | `RabbitMQ node probe OK`     | `alias`, `node`, `seconds`          |
| Узел отказал     | `warning` | `RabbitMQ node probe failed` | `alias`, `node`, `error`, `seconds` |
| Алиас недоступен | `warning` | `RabbitMQ connection failed` | `alias`, `error`, `seconds`         |

Значение `seconds` в логах округляется до 3 знаков.

- Предупреждение об узле может появиться, даже если алиас в итоге `ok` (ответил другой узел) — если поток отказавшего
  узла успел завершиться до выхода процесса. Само по себе оно не означает, что алиас недоступен.
- В `error` предупреждения об узле — ошибка именно этого узла (без префикса `host:port`), а в `error` предупреждения об
  алиасе — объединённая строка по всем узлам.
- Предупреждения об узлах предшествуют предупреждению об алиасе.

### Диагностика таймаутов хелсчека

Раньше при таймауте было видно лишь сообщение `Health check exceeded timeout (10s)` с ANSI-кодами и дублирующимися
строками `OK: <alias>` / `ok: <alias>` — понять, на что ушло время, было нельзя. Теперь каждая строка печатается сразу,
и последняя видимая строка показывает этап, на котором остановилась проба.

Начиная с версии 1.1.6 команда сама ограничивает фазу проверки дедлайном: вместо того чтобы быть убитой по таймауту
оркестратора, она печатает `UNHEALTHY` и ошибку `TimeoutError`. Это работает, только если таймаут пробы не меньше
`startup` + `DEADLINE` — см. Бюджет времени хелсчека.

| Последняя напечатанная строка | На что ушло время                                                                                                                                                                                                                                                         |
|-------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| *(ничего)*                    | Python и Django ещё запускались (интерпретатор, импорты, `django.setup()`); при `uv run` — ещё и сам `uv`                                                                                                                                                                 |
| `startup`                     | Ни один алиас ещё не получил вердикт: все узлы всех алиасов всё ещё подключались. Команда остановилась бы сама по достижении `DEADLINE`; если её убили раньше, таймаут пробы меньше `startup` + `DEADLINE` — увеличьте таймаут пробы или уменьшите `DEADLINE` / `--timeout` |
| Несколько строк `check`       | Алиасы, которых нет среди напечатанных строк (сравните с конфигурацией), всё ещё ждали ответа от узла. Средство то же                                                                                                                                                      |
| `summary` / `ERROR`           | Завершение процесса после проверки (обработчики `atexit`, не-daemon потоки **вашего** проекта). Потоки проб — daemon и процесс не удерживают                                                                                                                               |

Как читать числа:

- Большое значение `startup` — время уходит на запуск Django, брокер здесь ни при чём. Увеличьте таймаут пробы или
  ускорьте старт приложения. Системные проверки уже исключены, так что остаётся запуск интерпретатора, импорты и
  `django.setup()` (включая `AppConfig.ready()` ваших приложений).
- `seconds` в событии `check` со статусом `ok` — время самого быстрого ответившего узла.
- `FAIL` с `took`, близким к `DEADLINE`, и ошибкой `TimeoutError` — за время дедлайна ни один узел не ответил; узлы с
  пометкой `no answer` зависли (пакеты отбрасываются или не завершается рукопожатие).
- `FAIL` с `took` заметно меньше `DEADLINE` — все узлы вернули ошибки; читайте ошибки по узлам.
- Эвристика: обычно `took`, близкий к `SOCKET_TIMEOUT` пробы, означает, что пакеты отбрасываются, а близкий к
  `STACK_TIMEOUT` — что зависает рукопожатие. Реальный пример: недоступный узел (пакеты отбрасываются) плюс закрытый
  порт дали `took=5.01s` при `SOCKET_TIMEOUT` пробы, равном 5.

Будет ли виден частичный вывод пробы, убитой по таймауту, зависит от оркестратора. Надёжный способ — запустить команду
вручную в контейнере:

```bash
docker exec <container> /app/.venv/bin/python /app/manage.py check_rabbitmq_connections --format text
docker exec <container> /app/.venv/bin/python /app/manage.py check_rabbitmq_connections --format text --timeout 2
```

Второй вариант с `--timeout 2` удобен для быстрой ручной проверки: команда уложится примерно в две секунды.

## Запуск в production

Типовая production-конфигурация запускает `setup_rabbitmq_topology` один раз при деплое, а затем поддерживает
`start_consumers` в качестве долго живущего процесса под управлением супервизора процессов (systemd, Docker, Kubernetes
и др.).

**Пример systemd-юнита:**

```ini
[Unit]
Description = Django RMQ Consumers
After = network.target

[Service]
WorkingDirectory = /app
ExecStartPre = uv run python manage.py setup_rabbitmq_topology
ExecStart = uv run python manage.py start_consumers
Restart = on-failure
KillSignal = SIGTERM
TimeoutStopSec = 30

[Install]
WantedBy = multi-user.target
```

**Пример Docker:**

```dockerfile
CMD ["uv", "run", "python", "manage.py", "start_consumers"]
```

Запускайте `setup_rabbitmq_topology` в отдельном init-контейнере или в хуке деплоя, чтобы топология была объявлена до
того, как потребители попытаются привязаться к очередям.

Используйте `check_rabbitmq_connections` в качестве readiness/liveness-пробы — команда завершается с ненулевым кодом,
когда брокер недоступен. Рекомендации:

- Запускайте интерпретатор виртуального окружения напрямую (`/app/.venv/bin/python`), а не `uv run`: `uv run`
  проверяет и синхронизирует окружение перед каждым запуском, а это задержка при каждом вызове пробы, которая не
  попадает в `startup`.
- Если проба всё же запускается через `uv run`, добавьте `--no-sync`
  (`uv run --no-sync python manage.py check_rabbitmq_connections`) или задайте переменную окружения `UV_NO_SYNC=1`:
  тогда uv не обновляет lock-файл и не синхронизирует окружение при каждом вызове. Запуск самого `uv` всё равно
  занимает время, которое не попадает в `startup`, поэтому предпочтительнее интерпретатор виртуального окружения.
- Передавать `--skip-checks` больше не нужно: команда никогда не запускает системные проверки Django. Флаг по-прежнему
  принимается, так что существующие описания проб продолжат работать.
- Задавайте таймаут пробы с запасом на старт Django и на дедлайн команды: он должен быть не меньше `startup` +
  `DEADLINE` + запас (см. Бюджет времени хелсчека). Ориентир для `startup` — значение из
  реального вывода команды в вашем окружении.
- В Kubernetes явно указывайте `timeoutSeconds`: по умолчанию он равен 1 секунде, что почти всегда меньше времени
  старта Django.
- Путь `/app` приведён для примера — согласуйте его со своим `WORKDIR`.

### Бюджет времени хелсчека

Проба укладывается в свой таймаут, только если он не меньше суммы:

```
таймаут пробы >= startup + DEADLINE + запас
```

Значения по умолчанию рассчитаны на таймаут 25 секунд: `startup` до ~8 секунд, `DEADLINE` 15 секунд и запас.
Команду пробы менять не нужно — достаточно выставить таймаут не меньше этого бюджета.

Почему это важно: в одном из production-кластеров алиас с `SHUFFLE_NODES` содержал недоступные узлы, и каждый из них
обходился в 10–15 секунд (см. Таймауты узлов и время failover). Старый хелсчек подключался
к узлам последовательно, поэтому время зависело от случайного порядка узлов и периодически упиралось в таймаут пробы
в 10 секунд, хотя RabbitMQ работал. Теперь узлы проверяются параллельно, а общее время ограничено `DEADLINE`; таймаут
Docker-пробы в production увеличен с 10 до 25 секунд.

Если таймаут пробы поднять нельзя (например, строгий `timeoutSeconds` в Kubernetes), уменьшите `DEADLINE` в
`RABBITMQ_HEALTHCHECK` или передайте `--timeout`. Пример значений (подберите под свою сеть):

```python
RABBITMQ_HEALTHCHECK = {'DEADLINE': 8.0, 'SOCKET_TIMEOUT': 3.0, 'STACK_TIMEOUT': 6.0}
```

Держите таймауты на узел (`SOCKET_TIMEOUT`, `STACK_TIMEOUT`) не больше `DEADLINE`, иначе зависший узел будет
показан как `no answer`, а не со своей ошибкой. Подробнее о настройке — в разделе
`RABBITMQ_HEALTHCHECK`.

**Пример Kubernetes:**

```yaml
livenessProbe:
  exec:
    command: [ "uv", "run", "/app/manage.py", "check_rabbitmq_connections" ]
  periodSeconds: 30
  timeoutSeconds: 25
  failureThreshold: 3
```
