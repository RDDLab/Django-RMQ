---
title: Реестры
order: 7
---

# Реестры

Реестры — это хранящиеся в памяти коллекции, с помощью которых библиотека отслеживает для каждого алиаса подключения: какие потребители должны запускаться и какие функции настройки топологии необходимо выполнять. Они создаются автоматически в `RabbitMQAppConfig.ready()` — по одному реестру каждого типа на каждый настроенный алиас.

Существует два типа реестров:

- **`ConsumersRegistry`** — хранит экземпляры `Consumer`; используется командой `start_consumers`.
- **`SetupRegistry`** — хранит вызываемые объекты `SetupFn`; используется командой `setup_rabbitmq_topology`.

## ConsumersRegistry

`ConsumersRegistry` хранит потребителей, которые будет запускать команда управления `start_consumers`.

```python
from django_rmq.registries.registry import ConsumersRegistry, get_consumers_registry
```

### API

| Метод / Функция | Сигнатура | Описание |
|-----------------|-----------|----------|
| `register` | `(consumer: Consumer) -> None` | Добавляет потребителя в реестр. |
| `all` | `() -> list[Consumer]` | Возвращает копию списка зарегистрированных потребителей. |
| `get_consumers_registry` | `(using: str \| None = None) -> ConsumersRegistry` | Вспомогательная функция уровня модуля, возвращающая реестр для указанного алиаса. |

`all()` всегда возвращает новый список, поэтому вызывающий код не может изменить внутреннее состояние реестра.

### Регистрация потребителя

Определите потребителя и его обработчик в отдельном модуле — например, `orders/consumers.py`:

```python
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import (
    Basic,
    BasicProperties
)

from django_rmq.consumer import Consumer
from django_rmq.queues.queue_config import QueueConfig

queue: QueueConfig = QueueConfig(name='orders')
consumer: Consumer = Consumer(queue=queue, prefetch_count=5)


@consumer.handler
def handle_order(
    channel: BlockingChannel,
    method: Basic.Deliver,
    properties: BasicProperties,
    body: bytes,
) -> None:
    # обработка сообщения
    channel.basic_ack(delivery_tag=method.delivery_tag)
```

Затем зарегистрируйте его в методе `ready()` одного из классов `AppConfig` вашего приложения — после инициализации `django_rmq`:

```python
from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = 'orders'

    def ready(self) -> None:
        from django_rmq.registries.registry import get_consumers_registry

        from orders.consumers import consumer

        get_consumers_registry().register(consumer=consumer)
```

### Использование с несколькими алиасами

Если настроено несколько подключений, передайте `using`, чтобы обратиться к нужному реестру:

```python
from django_rmq.consumer import Consumer
from django_rmq.registries.registry import get_consumers_registry

analytics_consumer: Consumer = Consumer(queue='events', using='analytics')
get_consumers_registry(using='analytics').register(consumer=analytics_consumer)
```

## SetupRegistry

`SetupRegistry` хранит вызываемые объекты `SetupFn` — функции, объявляющие на брокере обмены, очереди и привязки. Команда `setup_rabbitmq_topology` открывает канал для каждого алиаса и вызывает `run_all`, выполняя все зарегистрированные функции.

```python
from django_rmq.registries.setup_registry import SetupRegistry, SetupFn, get_setup_registry
```

### Псевдоним типа `SetupFn`

```python
from collections.abc import Callable
from pika.adapters.blocking_connection import BlockingChannel

SetupFn = Callable[[BlockingChannel], None]
```

`SetupFn` получает открытый `BlockingChannel` и должна быть **идемпотентной** — объявления топологии RabbitMQ являются passive-safe, поэтому повторный вызов той же функции при повторном деплое не вызывает ошибок.

### API

| Метод / Функция | Сигнатура | Описание |
|-----------------|-----------|----------|
| `register` | `(fn: SetupFn) -> None` | Добавляет функцию настройки в реестр. |
| `run_all` | `(channel: BlockingChannel) -> None` | Вызывает все зарегистрированные функции в порядке их регистрации. |
| `get_setup_registry` | `(using: str \| None = None) -> SetupRegistry` | Вспомогательная функция уровня модуля, возвращающая реестр для указанного алиаса. |

Функции вызываются в порядке их регистрации.

### Регистрация функции настройки

```python
from django.apps import AppConfig
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType

from django_rmq.registries.setup_registry import get_setup_registry


class OrdersConfig(AppConfig):
    name = 'orders'

    def ready(self) -> None:
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

        get_setup_registry().register(fn=setup_orders_topology)
```

### Использование с несколькими алиасами

```python
from pika.adapters.blocking_connection import BlockingChannel

from django_rmq.registries.setup_registry import get_setup_registry


def setup_analytics(channel: BlockingChannel) -> None:
    channel.queue_declare(queue='events', durable=True)


get_setup_registry(using='analytics').register(fn=setup_analytics)
```

## Разрешение алиасов

Функции `get_consumers_registry` и `get_setup_registry` внутренне делегируют разрешение алиаса `resolve_alias`:

- Если настроен ровно один алиас, `using` можно не указывать.
- Если настроено несколько алиасов, `using` обязателен; его отсутствие вызовет `ImproperlyConfigured`.
- Передача неизвестного алиаса вызовет `ImproperlyConfigured`.

```python
from django_rmq.registries.registry import get_consumers_registry
from django_rmq.registries.setup_registry import get_setup_registry

# single alias — using omitted
consumers = get_consumers_registry()
setup = get_setup_registry()

# multiple aliases — using required
default_consumers = get_consumers_registry(using='default')
analytics_setup = get_setup_registry(using='analytics')

# different aliases always return different registry objects
assert default_consumers is not get_consumers_registry(using='analytics')
```

## Жизненный цикл

Реестры создаются пустыми в `RabbitMQAppConfig.ready()` при запуске Django. Они заполняются на той же фазе запуска, когда выполняются методы `AppConfig.ready()` ваших приложений. После запуска реестры являются доступными только для чтения с точки зрения библиотеки — `start_consumers` и `setup_rabbitmq_topology` лишь вызывают `all()` и `run_all()`, не изменяя списки.

Регистрация потребителя или функции настройки после запуска Django (например, внутри представления) технически работает, однако такие записи не будут обработаны командами управления в текущем процессе, если команда уже запущена.
