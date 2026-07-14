---
title: Consumers
order: 5
---

# Consumers

A `Consumer` subscribes to a single RabbitMQ queue with one registered handler function. It reconnects automatically on
transient AMQP errors, polls a `stop_event` for graceful shutdown, and closes stale Django database connections before
each message dispatch.

## Creating a Consumer

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

**Parameters**

| Parameter                   | Type                 | Default | Description                                                                                       |
|-----------------------------|----------------------|---------|---------------------------------------------------------------------------------------------------|
| `queue`                     | `QueueConfig \| str` | —       | Queue to consume from. Determines declaration mode (see [Queue Declaration](#queue-declaration)). |
| `prefetch_count`            | `int`                | `1`     | Maximum unacknowledged messages delivered at once (`basic_qos`).                                  |
| `reconnect_initial_backoff` | `float \| None`      | `None`  | Initial reconnect wait in seconds. Falls back to the connection config when `None`.               |
| `reconnect_max_backoff`     | `float \| None`      | `None`  | Maximum reconnect wait in seconds. Falls back to the connection config when `None`.               |
| `using`                     | `str \| None`        | `None`  | Connection alias from `RABBITMQ_CONNECTIONS`. Omit for a single-connection setup.                 |

A `Consumer` can be created at module level — it does not open a connection on `__init__`. The connection is obtained
when `consume()` is called.

## Registering a Handler

Each consumer accepts **exactly one** handler. Attempting to register a second handler raises `RuntimeError`.

### Using `consumer.handler` as a decorator

```python
import json
from typing import Any

from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

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

### Using the consumer instance directly (`__call__` shorthand)

`@consumer` is equivalent to `@consumer.handler`:

```python
from typing import Any

from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

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

**Handler signature** — `MessageCallback`:

```python
from collections.abc import Callable
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

MessageCallback = Callable[[BlockingChannel, Basic.Deliver, BasicProperties, bytes], None]
```

## Acknowledgements

Django-RMQ does **not** auto-acknowledge messages. Your handler is responsible for calling `ch.basic_ack` or
`ch.basic_nack` on every delivery.

**On success** — always call `basic_ack`:

```python
ch.basic_ack(delivery_tag=method.delivery_tag)
```

**On a known, unrecoverable message error** — call `basic_nack` without requeue to send the message to the dead-letter
exchange (if configured):

```python
ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
```

**On an unhandled exception** — the consumer's internal dispatcher catches the exception, logs it, and calls
`basic_nack(requeue=False)` automatically. You do not need to nack inside an `except` block for this case.

Never call both `basic_ack` and `basic_nack` for the same `delivery_tag`.

## Queue Declaration

When `consume()` starts a new session, the consumer declares the queue before entering the consume loop. The declaration
mode depends on the `queue` argument:

| `queue` type      | Declaration                                                                                                                       |
|-------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| `str` (non-empty) | `queue_declare(queue=name, durable=True)` — creates a durable queue if absent.                                                    |
| `QueueConfig`     | `queue_declare(queue=name, durable=config.durable, arguments=config.arguments)` — active declare including dead-letter arguments. |

Unlike the producer (which uses `passive=True` for string queues), the consumer always declares actively so that the
queue exists before consuming begins.

## Running a Consumer

Call `consume()` to start the blocking consume loop. Pass a `threading.Event` to support graceful shutdown:

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

The loop polls `stop_event` approximately once per second (`process_data_events(time_limit=1)`). When the event is set,
the loop exits, the channel is stopped and closed cleanly.

If `stop_event` is not provided, an internal event is created that is never set — the consumer runs until an
unrecoverable error or process termination.

In production, use the `start_consumers` management command instead of calling `consume()` directly.
See [Management Commands](/en/1.0.4/management-commands.html).

## Reconnect Behavior

On a transient AMQP error (`AMQPConnectionError`, `ConnectionClosed`, `ChannelClosed`, `ChannelClosedByBroker`,
`StreamLostError`, `ConnectionResetError`), the consumer:

1. Logs a warning.
2. Waits `backoff` seconds (`stop_event.wait(timeout=backoff)` — instant wakeup on shutdown).
3. Doubles the delay: `backoff = min(backoff * 2, reconnect_max_backoff)`.
4. Opens a new connection and declares the queue again.

The initial backoff and cap come from the connection config (`RECONNECT_INITIAL_BACKOFF`, `RECONNECT_MAX_BACKOFF`)
unless overridden in the constructor.

Non-reconnectable exceptions propagate immediately without a retry.

## Django DB Connections

Consumer threads are long-lived. Django's default database connection handling assumes short-lived request/response
cycles. Before each message dispatch the consumer calls `django.db.close_old_connections()` to release any stale
database sockets that the server may have already closed on its side. This happens transparently — you do not need to
call it in your handler.

## Dead-Letter on Handler Failure

When your handler raises an unhandled exception, the dispatcher calls
`ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)`. The message is **not requeued**. If the queue is
configured with a dead-letter exchange (`QueueConfig.dead_letter_exchange`), the broker routes the message there
automatically.

See [Topology](/en/1.0.4/topology.html) for the full dead-letter topology setup and [Reliability](/en/1.0.4/reliability.html) for
the delivery guarantees.

Example — a handler that always fails routes messages to the DLQ:

```python
import json
from typing import Any

from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

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

## Properties

| Property                  | Type          | Description                                                                  |
|---------------------------|---------------|------------------------------------------------------------------------------|
| `consumer.prefetch_count` | `int`         | Maximum unacknowledged deliveries in flight.                                 |
| `consumer.using`          | `str \| None` | Connection alias, or `None` for the implicit single connection.              |
| `consumer.handler_name`   | `str`         | Name of the registered handler function, or `'unregistered'` if none is set. |

## Registering with the Consumers Registry

To have `start_consumers` pick up your consumer automatically, register it in `ConsumersRegistry`. The recommended place
is your app's `AppConfig.ready()`:

```python
from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = 'orders'

    def ready(self) -> None:
        from django_rmq.registries.registry import get_consumers_registry

        from orders.consumers import consumer  # the Consumer instance with a handler

        get_consumers_registry().register(consumer=consumer)
```

See [Registries](/en/1.0.4/registries.html) for the full registration pattern.

## See Also

- [Topology](/en/1.0.4/topology.html) — declare queues and dead-letter exchanges.
- [Reliability](/en/1.0.4/reliability.html) — delivery model and reconnect details.
- [Management Commands](/en/1.0.4/management-commands.html) — `start_consumers` in production.
- [Registries](/en/1.0.4/registries.html) — `ConsumersRegistry` lifecycle.
- [API Reference](/en/1.0.4/api-reference.html) — complete `Consumer` signature.
