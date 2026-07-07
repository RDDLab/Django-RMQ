---
title: Потребители
order: 5
---

# Потребители

`Consumer` подписывается на одну очередь RabbitMQ с одной зарегистрированной функцией-обработчиком. Он автоматически
переподключается при временных AMQP-ошибках, опрашивает `stop_event` для корректного завершения работы и закрывает
устаревшие соединения с базой данных Django перед каждой отправкой сообщения.

## Создание потребителя

```python
from django_rmq.consumer import Consumer
from django_rmq.queues.queue_config import QueueConfig

# Plain string queue name
consumer: Consumer = Consumer(queue='orders')

# QueueConfig — carries durability and dead-letter settings
queue_config: QueueConfig = QueueConfig(
    name='orders',
    dead_letter_exchange='dlx-orders',
    dead_letter_routing_key='dlq-orders',
)
consumer: Consumer = Consumer(queue=queue_config)

# Override prefetch and backoff
consumer: Consumer = Consumer(
    queue='orders',
    prefetch_count=5,
    reconnect_initial_backoff=0.5,
    reconnect_max_backoff=30.0,
)

# Explicit connection alias
consumer: Consumer = Consumer(queue='orders', using='payments')
```

**Параметры**

| Параметр                    | Тип                  | По умолчанию | Описание                                                                                                              |
|-----------------------------|----------------------|--------------|-----------------------------------------------------------------------------------------------------------------------|
| `queue`                     | `QueueConfig \| str` | —            | Очередь для чтения. Определяет режим объявления (см. [Объявление очереди](#объявление-очереди)).                      |
| `prefetch_count`            | `int`                | `1`          | Максимальное количество неподтверждённых сообщений, доставляемых одновременно (`basic_qos`).                          |
| `reconnect_initial_backoff` | `float \| None`      | `None`       | Начальное время ожидания переподключения в секундах. При `None` используется значение из конфигурации подключения.    |
| `reconnect_max_backoff`     | `float \| None`      | `None`       | Максимальное время ожидания переподключения в секундах. При `None` используется значение из конфигурации подключения. |
| `using`                     | `str \| None`        | `None`       | Псевдоним подключения из `RABBITMQ_CONNECTIONS`. Не указывайте при настройке с одним подключением.                    |

`Consumer` можно создавать на уровне модуля — при `__init__` подключение не открывается. Соединение получается при
вызове `consume()`.

## Регистрация обработчика

Каждый потребитель принимает **ровно один** обработчик. При попытке зарегистрировать второй обработчик произойдет
исключение `RuntimeError`.

### Использование `consumer.handler` как декоратора

```python
import json
from typing import Any

from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic,
    BasicProperties

from django_rmq.consumer import Consumer

consumer: Consumer = Consumer(queue='orders')


@consumer.handler
def handle_order(
    ch: BlockingChannel,
    method: Basic.Deliver,
    props: BasicProperties,
    body: bytes,
) -> None:
    data: dict[str, Any] = json.loads(body)
    # process the message ...
    ch.basic_ack(delivery_tag=method.delivery_tag)
```

### Прямое использование экземпляра потребителя (сокращение `__call__`)

`@consumer` эквивалентно `@consumer.handler`:

```python
from typing import Any

from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic,
    BasicProperties

from django_rmq.consumer import Consumer

consumer: Consumer = Consumer(queue='payments')


@consumer
def handle_payment(
    ch: BlockingChannel,
    method: Basic.Deliver,
    props: BasicProperties,
    body: bytes,
) -> None:
    # process the message ...
    ch.basic_ack(delivery_tag=method.delivery_tag)
```

**Сигнатура обработчика** — `MessageCallback`:

```python
from collections.abc import Callable
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic,
    BasicProperties

MessageCallback = Callable[[BlockingChannel, Basic.Deliver, BasicProperties, bytes], None]
```

## Подтверждения

Django-RMQ **не** подтверждает сообщения автоматически (`auto-ack`). Ваш обработчик обязан вызывать `ch.basic_ack` или
`ch.basic_nack` для каждого доставленного сообщения.

**При успехе** — всегда вызывайте `basic_ack`:

```python
ch.basic_ack(delivery_tag=method.delivery_tag)
```

**При известной, невосстанавливаемой ошибке сообщения** — вызывайте `basic_nack` без повторной постановки в очередь,
чтобы отправить сообщение в dead-letter exchange (если настроен):

```python
ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
```

**При необработанном исключении** — внутренний диспетчер потребителя перехватывает исключение, логирует его и
автоматически вызывает `basic_nack(requeue=False)`. В этом случае не нужно вызывать nack внутри блока `except`.

Никогда не вызывайте одновременно `basic_ack` и `basic_nack` для одного и того же `delivery_tag`.

## Объявление очереди

Когда `consume()` запускает новую сессию, потребитель объявляет очередь перед входом в цикл потребления. Режим
объявления зависит от аргумента `queue`:

| Тип `queue`      | Объявление                                                                                                                       |
|------------------|----------------------------------------------------------------------------------------------------------------------------------|
| `str` (непустая) | `queue_declare(queue=name, durable=True)` — создаёт durable очередь, если отсутствует.                                           |
| `QueueConfig`    | `queue_declare(queue=name, durable=config.durable, arguments=config.arguments)` — активное объявление с аргументами dead-letter. |

В отличие от продюсера (который использует `passive=True` для строковых очередей), потребитель всегда объявляет активно,
чтобы очередь существовала до начала потребления.

## Запуск потребителя

Вызовите `consume()` для запуска блокирующего цикла потребления. Передайте `threading.Event` для поддержки корректного
завершения работы:

```python
import threading

from django_rmq.consumer import Consumer

consumer: Consumer = Consumer(queue='orders')


@consumer
def handle_order(ch, method, props, body: bytes) -> None:
    ch.basic_ack(delivery_tag=method.delivery_tag)


stop_event: threading.Event = threading.Event()
# In production, start_consumers management command manages this for you.
consumer.consume(stop_event=stop_event)
```

Цикл опрашивает `stop_event` приблизительно раз в секунду (`process_data_events(time_limit=1)`). Когда событие
установлено, цикл завершается, канал останавливается и корректно закрывается.

Если `stop_event` не передан, создаётся внутреннее событие, которое никогда не устанавливается — потребитель работает до
невосстанавливаемой ошибки или завершения процесса.

В production используйте management-команду `start_consumers` вместо прямого вызова `consume()`.
См. [Management-команды](/ru/management-commands.html).

## Поведение при переподключении

При временной AMQP-ошибке (`AMQPConnectionError`, `ConnectionClosed`, `ChannelClosed`, `ChannelClosedByBroker`,
`StreamLostError`, `ConnectionResetError`) потребитель:

1. Записывает предупреждение в лог.
2. Ждёт `backoff` секунд (`stop_event.wait(timeout=backoff)` — мгновенное пробуждение при завершении).
3. Удваивает задержку: `backoff = min(backoff * 2, reconnect_max_backoff)`.
4. Открывает новое соединение и повторно объявляет очередь.

Начальная задержка и максимум берутся из конфигурации подключения (`RECONNECT_INITIAL_BACKOFF`,
`RECONNECT_MAX_BACKOFF`), если не переопределены в конструкторе.

Невосстанавливаемые исключения передаются немедленно без повтора.

## Соединения с базой данных Django

Потоки потребителей являются долгоживущими. Стандартная обработка соединений с базой данных в Django рассчитана на
короткий цикл запрос/ответ. Перед каждой отправкой сообщения потребитель вызывает `django.db.close_old_connections()`
для освобождения устаревших сокетов базы данных, которые сервер мог уже закрыть со своей стороны. Это происходит
прозрачно — вам не нужно вызывать это в обработчике.

## Dead-letter при ошибке обработчика

Когда обработчик выбрасывает необработанное исключение, диспетчер вызывает
`ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)`. Сообщение **не помещается обратно в очередь**. Если
очередь настроена с dead-letter exchange (`QueueConfig.dead_letter_exchange`), брокер автоматически маршрутизирует
сообщение туда.

См. [Топологию](/ru/topology.html) для настройки полной dead-letter топологии и [Надёжность](/ru/reliability.html) для
гарантий доставки.

Пример — обработчик, который всегда завершается с ошибкой и маршрутизирует сообщения в DLQ:

```python
import json
from typing import Any

from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic,
    BasicProperties

from django_rmq.consumer import Consumer
from django_rmq.queues.queue_config import QueueConfig

queue_config: QueueConfig = QueueConfig(
    name='orders',
    dead_letter_exchange='dlx-orders',
    dead_letter_routing_key='dlq-orders',
)
consumer: Consumer = Consumer(queue=queue_config)


@consumer
def handle_order(
    ch: BlockingChannel,
    method: Basic.Deliver,
    props: BasicProperties,
    body: bytes,
) -> None:
    data: dict[str, Any] = json.loads(body)
    if data.get('corrupted'):
        # Raise — dispatcher will nack without requeue -> DLX
        raise ValueError(f'Corrupted message: {body!r}')
    ch.basic_ack(delivery_tag=method.delivery_tag)
```

## Свойства

| Свойство                  | Тип           | Описание                                                                                        |
|---------------------------|---------------|-------------------------------------------------------------------------------------------------|
| `consumer.prefetch_count` | `int`         | Максимальное количество неподтверждённых доставок в обработке.                                  |
| `consumer.using`          | `str \| None` | Псевдоним подключения или `None` для неявного единственного подключения.                        |
| `consumer.handler_name`   | `str`         | Имя зарегистрированной функции-обработчика или `'unregistered'`, если обработчик не установлен. |

## Регистрация в реестре потребителей

Чтобы `start_consumers` автоматически обнаружил вашего потребителя, зарегистрируйте его в `ConsumersRegistry`.
Рекомендуемое место — метод `AppConfig.ready()` вашего приложения:

```python
from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = 'orders'

    def ready(self) -> None:
        from django_rmq.registries.registry import get_consumers_registry

        from orders.consumers import consumer  # the Consumer instance with a handler

        get_consumers_registry().register(consumer=consumer)
```

См. [Реестры](/ru/registries.html) для полного описания паттерна регистрации.

## Смотрите также

- [Топология](/ru/topology.html) — объявление очередей и dead-letter exchanges.
- [Надёжность](/ru/reliability.html) — модель доставки и детали переподключения.
- [Management-команды](/ru/management-commands.html) — `start_consumers` в production.
- [Реестры](/ru/registries.html) — жизненный цикл `ConsumersRegistry`.
- [Справочник API](/ru/api-reference.html) — полная сигнатура `Consumer`.
