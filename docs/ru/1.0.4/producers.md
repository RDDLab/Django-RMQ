---
title: Продюсеры
order: 4
---

# Продюсеры

`Producer` публикует сообщения в RabbitMQ через потокозависимый блокирующий канал. Один экземпляр привязывается к
конкретному exchange и очереди при создании и переиспользует эту привязку при каждом вызове `publish`.

## Создание продюсера

```python
from django_rmq.producer import Producer
from django_rmq.queues.queue_config import QueueConfig

# Default exchange, queue named by string
producer: Producer = Producer(queue='orders')

# Named exchange, no fixed queue (exchange-only mode)
producer: Producer = Producer(exchange='events', queue='')

# With a QueueConfig (carries dead-letter settings)
queue_config: QueueConfig = QueueConfig(
    name='orders',
    dead_letter_exchange='dlx-orders',
    dead_letter_routing_key='dlq-orders',
)
producer: Producer = Producer(queue=queue_config)

# Explicit connection alias (required when multiple connections are configured)
producer: Producer = Producer(queue='orders', using='payments')
```

**Параметры**

| Параметр   | Тип                  | По умолчанию | Описание                                                                                                                                                        |
|------------|----------------------|--------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `exchange` | `str`                | `''`         | Имя exchange. Пустая строка означает exchange по умолчанию (direct).                                                                                            |
| `queue`    | `QueueConfig \| str` | `''`         | Очередь для публикации. Используется также как ключ маршрутизации по умолчанию. Передайте пустую строку для публикации только в exchange с явным `routing_key`. |
| `using`    | `str \| None`        | `None`       | Псевдоним подключения из `RABBITMQ_CONNECTIONS`. Не указывайте, если настроено одно подключение.                                                                |

`Producer` можно создавать на уровне модуля — при `__init__` подключение не открывается. Соединение и канал получаются
лениво при первом вызове `publish`.

## Публикация сообщения

```python
import json
from django_rmq.producer import Producer

producer: Producer = Producer(queue='orders')

# String body — encoded to UTF-8 bytes automatically
producer.publish(body='{"order_id": 42}')

# Bytes body — passed through unchanged
producer.publish(body=b'{"order_id": 42}')

# Override routing key (exchange-only mode)
Producer(exchange='events', queue='').publish(
    body=json.dumps({'event': 'order.created'}),
    routing_key='payments.created',
)
```

**Сигнатура `publish`**

```python
def publish(
    self,
    body: str | bytes,
    routing_key: str | None = None,
    properties: BasicProperties | None = None,
) -> None: ...
```

- `body` — `str` кодируется в UTF-8; `bytes` отправляется без изменений.
- `routing_key` — если не указан, используется `self.queue` (имя очереди).
- `properties` — свойства AMQP-сообщения; см. [Пользовательские свойства](#пользовательские-свойства) ниже.

## Постоянная доставка (Persistent Delivery)

Каждое сообщение, опубликованное через `Producer`, является **постоянным** (`delivery_mode=2`). Это означает, что брокер
записывает сообщение на диск, и оно переживает перезапуск брокера при условии, что сама очередь является durable.

Если передать объект `BasicProperties` без указания `delivery_mode`, продюсер принудительно устанавливает
`DeliveryMode.Persistent`. Единственный способ отправить нестойкое сообщение — явно указать
`delivery_mode=DeliveryMode.Transient` в объекте свойств.

```python
from pika import DeliveryMode
from pika.spec import BasicProperties
from django_rmq.producer import Producer

# Explicitly transient (unusual — only if you know what you are doing)
Producer(queue='ephemeral').publish(
    body='ping',
    properties=BasicProperties(delivery_mode=DeliveryMode.Transient.value),
)
```

## Ленивое объявление очереди

Очередь объявляется на брокере **один раз, при первом вызове `publish`**. После этого флаг
`_is_queue_declared` предотвращает повторные объявления.

Режим объявления зависит от типа аргумента `queue`:

| Тип `queue`          | Режим объявления                              | Эффект                                                                                            |
|----------------------|-----------------------------------------------|---------------------------------------------------------------------------------------------------|
| `str` (непустая)     | `passive=True`                                | Проверяет наличие очереди; выбрасывает `ChannelClosedByBroker` (404), если очередь не существует. |
| `QueueConfig`        | Активное объявление с `durable` + `arguments` | Создаёт очередь, если отсутствует; идемпотентна при повторном вызове с теми же параметрами.       |
| `''` (пустая строка) | Пропускается полностью                        | Используйте явный `routing_key`; продюсер сразу переходит к `basic_publish`.                      |

Используйте `QueueConfig`, когда очередь имеет dead-letter аргументы или когда нужно, чтобы продюсер создал очередь,
если она ещё не существует. Используйте обычную строку, когда существование очереди гарантировано (объявлена
setup-функцией или другим сервисом).

## Надёжность: confirmation, mandatory и ретраи

**Подтверждения публикации** включены на каждом канале продюсера (`confirm_delivery()`). После каждого `basic_publish`
брокер подтверждает получение сообщения. Если ни одна очередь не соответствует ключу маршрутизации, брокер возвращает
сообщение, и pika выбрасывает `UnroutableError`.

**`mandatory=True`** всегда установлен. Сообщение, опубликованное в exchange без подходящей привязки, **не отбрасывается
молча** — брокер возвращает его, и pika выбрасывает `UnroutableError`.

```python
from pika.exceptions import UnroutableError
from django_rmq.producer import Producer

producer: Producer = Producer(exchange='', queue='')

try:
    producer.publish(body=b'nowhere', routing_key='no-such-queue')
except UnroutableError:
    # The broker had no queue for this routing key.
    ...
```

**Повтор при временных ошибках.** Когда `publish` сталкивается с AMQP-ошибкой (`AMQPConnectionError`,
`ConnectionClosed`, `ChannelClosed`, `ChannelClosedByBroker`, `StreamLostError`, `ConnectionResetError`), он сбрасывает
кэшированные канал и соединение, затем выполняет повтор **ровно один раз**. Если повтор также завершается неудачей,
исключение передаётся вызывающему коду.

Невосстанавливаемые исключения (например, `ValueError`, `UnroutableError`) не повторяются и немедленно передаются
вызывающему коду.

## Продюсер как декоратор

Экземпляр `Producer` может использоваться как декоратор функции. Декоратор автоматически публикует возвращаемое значение
функции после её выполнения.

```python
import json
from django_rmq.producer import Producer

order_producer: Producer = Producer(queue='orders')

@order_producer
def create_order(order_id: int) -> str:
    # business logic here
    return json.dumps({'order_id': order_id})

# Calling create_order publishes the returned JSON and also returns it.
result: str = create_order(order_id=42)
```

**Контракт возвращаемого значения:**

| Тип возврата      | Поведение                                     |
|-------------------|-----------------------------------------------|
| `str` или `bytes` | Публикуется и возвращается вызывающему коду.  |
| `None`            | Публикация пропускается; возвращается `None`. |
| Любой другой тип  | Немедленно выбрасывается `TypeError`.         |

Строгость в отношении других типов намеренна — молчаливая сериализация `dict` или `list` скрывала бы ошибки контракта.

## Публикация только в exchange

Для публикации в exchange без фиксированной очереди (например, fanout или topic exchange) установите `queue=''` и всегда
передавайте `routing_key` в `publish`:

```python
from django_rmq.producer import Producer

events_producer: Producer = Producer(exchange='domain.events', queue='')

events_producer.publish(
    body=b'{"type": "order.shipped", "order_id": 7}',
    routing_key='order.shipped',
)
```

В этом режиме объявление очереди не выполняется.

## Custom properties

Передайте экземпляр `BasicProperties`, чтобы переопределить тип контента, заголовки, correlation ID или другие
AMQP-свойства. `delivery_mode` принудительно устанавливается в `Persistent`, если вы явно не задаёте его.

```python
from pika.spec import BasicProperties
from django_rmq.producer import Producer

Producer(queue='orders').publish(
    body=b'{"order_id": 1}',
    properties=BasicProperties(
        content_type='application/json',
        correlation_id='req-abc-123',
        headers={'x-source': 'checkout-service'},
    ),
)
```

## Смотрите также

- [Топология](/ru/1.0.4/topology.html) — объявление exchanges и очередей с помощью `QueueConfig` и setup-функций.
- [Надёжность](/ru/1.0.4/reliability.html) — полная модель доставки, подтверждения и детали переподключения.
- [Несколько подключений](/ru/1.0.4/multiple-connections.html) — параметр `using`.
- [Справочник API](/ru/1.0.4/api-reference.html) — полная сигнатура `Producer`.
