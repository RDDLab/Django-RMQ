---
title: Топология
order: 6
---

# Топология

Прежде чем продюсеры и потребители смогут обмениваться сообщениями, необходимые объекты RabbitMQ — exchanges, очереди и
привязки — должны существовать на брокере. Django-RMQ предоставляет для этого два инструмента:

- **`QueueConfig`** — `frozen dataclass`, содержащий параметры объявления очереди (имя, долговечность, настройки
  dead-letter), используемый как продюсерами, так и потребителями.
- **`SetupRegistry` + setup-функции** — реестр вызываемых объектов, каждый из которых объявляет топологию на открытом
  AMQP-канале. Запускается один раз командой `setup_rabbitmq_topology`.

## `QueueConfig`

`QueueConfig` — `frozen dataclass`, определённый в `django_rmq.queues.queue_config`. Передавайте его вместо обычной
строки везде, где ожидается имя очереди.

```python
from django_rmq.queues.queue_config import QueueConfig

# Simple durable queue
orders_queue: QueueConfig = QueueConfig(name='orders')

# Durable queue wired to a dead-letter exchange
orders_queue: QueueConfig = QueueConfig(
    name='orders',
    durable=True,
    dead_letter_exchange='dlx-orders',
    dead_letter_routing_key='dlq-orders',
)
```

**Поля**

| Поле                      | Тип           | По умолчанию | Описание                                                  |
|---------------------------|---------------|--------------|-----------------------------------------------------------|
| `name`                    | `str`         | —            | Имя очереди. `str(queue_config)` возвращает это значение. |
| `durable`                 | `bool`        | `True`       | Переживает ли очередь перезапуск брокера.                 |
| `dead_letter_exchange`    | `str \| None` | `None`       | Устанавливает `x-dead-letter-exchange` при объявлении.    |
| `dead_letter_routing_key` | `str \| None` | `None`       | Устанавливает `x-dead-letter-routing-key` при объявлении. |

Свойство `.arguments` формирует словарь `x-dead-letter-*` для `queue_declare`. Возвращает `None`, если поля dead-letter
не заданы, что позволяет избежать передачи пустого словаря `arguments` брокеру.

### `QueueConfig` vs обычная строка

|                    | `QueueConfig`                                                                 | Обычная `str`                                                                            |
|--------------------|-------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| **Продюсер**       | Активное объявление (создаёт очередь, если отсутствует, передаёт `arguments`) | Пассивное объявление (`passive=True`) — выбрасывает исключение, если очередь отсутствует |
| **Потребитель**    | Активное объявление с `durable` + `arguments`                                 | Активное объявление, всегда `durable=True`, без дополнительных аргументов                |
| **Dead-letter**    | Поддерживается                                                                | Не поддерживается                                                                        |
| **Где определять** | В общем модуле `queues.py`                                                    | Inline, где удобно                                                                       |

Определяйте экземпляры `QueueConfig` в одном месте (например, `myapp/queues.py`) и импортируйте их в продюсеры,
потребители и setup-функции, чтобы имя очереди и настройки оставались согласованными.

## Setup-функции

Setup-функция — это любой вызываемый объект, принимающий единственный аргумент `BlockingChannel` и использующий его для
объявления exchanges, очередей и привязок:

```python
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType

from django_rmq.registries.setup_registry import SetupFn

def setup_orders_topology(channel: BlockingChannel) -> None:
    channel.exchange_declare(
        exchange='orders',
        exchange_type=ExchangeType.direct,
        durable=True,
    )
    channel.queue_declare(queue='orders', durable=True)
    channel.queue_bind(
        queue='orders',
        exchange='orders',
        routing_key='orders',
    )
```

`SetupFn` — это псевдоним типа:

```python
from collections.abc import Callable
from pika.adapters.blocking_connection import BlockingChannel

SetupFn = Callable[[BlockingChannel], None]
```

**Все setup-функции должны быть идемпотентными.** `exchange_declare` и `queue_declare` в RabbitMQ безопасно вызывать
несколько раз с одинаковыми параметрами — брокер игнорирует повторное объявление уже существующего объекта с идентичными
настройками. Двойной вызов `setup_rabbitmq_topology` не должен выбрасывать исключений.

## Регистрация setup-функций

Регистрируйте setup-функции внутри `AppConfig.ready()`, чтобы они были собраны до вызова `setup_rabbitmq_topology`:

```python
from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = 'orders'

    def ready(self) -> None:
        from django_rmq.registries.setup_registry import get_setup_registry

        from orders.topology import setup_orders_topology

        get_setup_registry().register(fn=setup_orders_topology)
```

При настройке с несколькими псевдонимами передайте `using` в `get_setup_registry`:

```python
get_setup_registry(using='payments').register(fn=setup_payments_topology)
```

## Запуск команды настройки

```bash
uv run python manage.py setup_rabbitmq_topology
```

С явным псевдонимом:

```bash
uv run python manage.py setup_rabbitmq_topology --using payments
```

Команда открывает один канал на каждый псевдоним подключения, вызывает все зарегистрированные setup-функции в порядке
регистрации, затем закрывает канал. Она сообщает о каждом объявленном объекте. Поскольку все объявления идемпотентны,
эту команду можно безопасно запускать в CI/CD пайплайнах и скриптах развёртывания.

См. [Management-команды](/ru/1.0.4/management-commands.html) для полного справочника команд.

## Пример dead-letter топологии

Dead-letter топология требует трёх компонентов:

1. Dead-letter exchange (DLX).
2. Dead-letter очередь (DLQ), привязанная к DLX.
3. Основная очередь, объявленная с `x-dead-letter-exchange`, указывающим на DLX.

Следующий пример повторяет интеграционный тест в `tests/integration/test_dlx.py`:

```python
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType

from django_rmq.consumer import Consumer
from django_rmq.producer import Producer
from django_rmq.queues.queue_config import QueueConfig
from django_rmq.registries.setup_registry import get_setup_registry

# 1. Define the queue config (main queue wired to the DLX)
orders_queue: QueueConfig = QueueConfig(
    name='orders',
    dead_letter_exchange='dlx-orders',
    dead_letter_routing_key='dlq-orders',
)


# 2. Register a setup function that declares the full topology
def setup_orders_dlx(channel: BlockingChannel) -> None:
    # Dead-letter exchange
    channel.exchange_declare(
        exchange='dlx-orders',
        exchange_type=ExchangeType.direct,
        durable=True,
    )
    # Dead-letter queue
    channel.queue_declare(queue='dlq-orders', durable=True)
    channel.queue_bind(
        queue='dlq-orders',
        exchange='dlx-orders',
        routing_key='dlq-orders',
    )
    # Main queue — declares with x-dead-letter-* arguments
    channel.queue_declare(
        queue='orders',
        durable=True,
        arguments={
            'x-dead-letter-exchange': 'dlx-orders',
            'x-dead-letter-routing-key': 'dlq-orders',
        },
    )


get_setup_registry().register(fn=setup_orders_dlx)


# 3. Producer uses the QueueConfig — active declare on first publish
producer: Producer = Producer(queue=orders_queue)


# 4. Consumer uses the QueueConfig — declares the queue with DLX arguments
consumer: Consumer = Consumer(queue=orders_queue)


@consumer
def handle_order(ch: BlockingChannel, method, props, body: bytes) -> None:
    # Raise to demonstrate DLX routing — dispatcher nacks without requeue
    raise ValueError('cannot process')
    # In normal operation call ch.basic_ack(delivery_tag=method.delivery_tag)
```

После выполнения `setup_rabbitmq_topology` любое сообщение, вызывающее исключение в `handle_order`, будет подтверждено с
nack без повторной постановки в очередь, и брокер маршрутизирует его в `dlq-orders` через `dlx-orders`.

## Смотрите также

- [Продюсеры](/ru/1.0.4/producers.html) — как `QueueConfig` влияет на объявление очереди в продюсере.
- [Потребители](/ru/1.0.4/consumers.html) — как `QueueConfig` влияет на объявление очереди в потребителе.
- [Реестры](/ru/1.0.4/registries.html) — жизненный цикл `SetupRegistry` и `get_setup_registry`.
- [Management-команды](/ru/1.0.4/management-commands.html) — справочник по `setup_rabbitmq_topology`.
- [Надёжность](/ru/1.0.4/reliability.html) — гарантии доставки dead-letter.
- [Справочник API](/ru/1.0.4/api-reference.html) — сигнатуры `QueueConfig` и `SetupRegistry`.
