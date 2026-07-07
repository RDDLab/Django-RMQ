---
title: Команды управления
order: 8
---

# Команды управления

Django-RMQ поставляется с тремя командами управления. `setup_rabbitmq_topology` и `start_consumers` расширяют
`RDDBaseCommand`; `check_rabbitmq_connections` — это лёгкий healthcheck, который намеренно его не расширяет.

## `setup_rabbitmq_topology`

Объявляет все обмены, очереди и привязки, зарегистрированные в [SetupRegistry](/ru/registries.html), для каждого алиаса
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

Запускает всех потребителей, зарегистрированных в [ConsumersRegistry](/ru/registries.html). Каждый потребитель
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

Команда-healthcheck, проверяющая доступность RabbitMQ. Для каждого алиаса открывает producer-соединение и сразу же
закрывает его, сообщая, какие алиасы доступны. Команда завершается с ненулевым кодом, если хотя бы одно соединение установить не
удалось, что делает её пригодной для readiness/liveness-проб.

```bash
uv run python manage.py check_rabbitmq_connections
```

### Параметры

| Параметр  | Тип   | По умолчанию | Описание                                                                                                       |
|-----------|-------|--------------|----------------------------------------------------------------------------------------------------------------|
| `--using` | `str` | `None`       | Алиас подключения из `RABBITMQ_CONNECTIONS` для проверки. Если не указан, проверяются все сконфигурированные алиасы. |

### Что делает команда

1. Проверяет, что django_rmq инициализирован — вызывает `ImproperlyConfigured`, если `django_rmq` отсутствует в
   `INSTALLED_APPS`.
2. Определяет список алиасов (`--using` выбирает один; в противном случае — все сконфигурированные алиасы).
3. Для каждого алиаса открывает producer-соединение и сразу же закрывает его:
   - При успехе выводит `OK: <alias>` (жирным зелёным) в stdout.
   - При ошибке (`AMQPError` или `OSError`) записывает предупреждение в лог и выводит `FAIL: <alias>` в stderr.
4. Если хотя бы один алиас недоступен, вызывает `CommandError` (код выхода 1) со списком недоступных алиасов.
5. Если все алиасы доступны, выводит итоговую строку `ok: <aliases>`.

### Пример вывода

```
  OK: default
  OK: analytics
ok: default, analytics
```

При ошибке:

```
  OK: default
  FAIL: analytics
CommandError: unhealthy: analytics
```

### Пример: проверка конкретного алиаса

```bash
uv run python manage.py check_rabbitmq_connections --using analytics
```

### Коды выхода

| Код | Значение                                                         |
|-----|------------------------------------------------------------------|
| `0` | Все проверенные алиасы доступны.                                 |
| `1` | Хотя бы один алиас недоступен (вызывается `CommandError`).       |

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
когда брокер недоступен:

```yaml
livenessProbe:
  exec:
    command: ["uv", "run", "python", "manage.py", "check_rabbitmq_connections"]
  periodSeconds: 30
```
