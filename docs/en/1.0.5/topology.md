---
title: Topology
order: 6
---

# Topology

Before producers and consumers can exchange messages, the required RabbitMQ objects — exchanges, queues, and bindings — must exist on the broker. Django-RMQ provides two tools for this:

- **`QueueConfig`** — a frozen dataclass that carries queue declaration parameters (name, durability, queue type, dead-letter settings) used by both producers and consumers.
- **`SetupRegistry` + setup functions** — a registry of callables, each of which declares topology on an open AMQP channel. Run once with `setup_rabbitmq_topology`.

## `QueueConfig`

`QueueConfig` is a frozen dataclass defined in `django_rmq.queues.queue_config`. Pass it instead of a plain string wherever a queue name is expected.

```python
from django_rmq.queues.queue_config import QueueConfig, QueueType

# Simple durable queue
orders_queue: QueueConfig = QueueConfig(name='orders')

# Durable queue wired to a dead-letter exchange
orders_queue: QueueConfig = QueueConfig(
    name='orders',
    durable=True,
    dead_letter_exchange='dlx-orders',
    dead_letter_routing_key='dlq-orders',
)

# Quorum queue
orders_queue: QueueConfig = QueueConfig(name='orders', queue_type=QueueType.QUORUM)
```

**Fields**

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | — | Queue name. `str(queue_config)` returns this value. |
| `durable` | `bool` | `True` | Whether the queue survives a broker restart. |
| `queue_type` | `QueueType \| None` | `None` | Sets `x-queue-type` on declaration. `None` lets the broker use its `default_queue_type`. |
| `dead_letter_exchange` | `str \| None` | `None` | Sets `x-dead-letter-exchange` on declaration. |
| `dead_letter_routing_key` | `str \| None` | `None` | Sets `x-dead-letter-routing-key` on declaration. |

The `.arguments` property builds the `x-queue-type` and `x-dead-letter-*` dict for `queue_declare`. It returns `None` when none of these fields are set, which avoids passing an empty `arguments` dict to the broker.

### `QueueConfig` vs a plain string

| | `QueueConfig` | Plain `str` |
|---|---|---|
| **Producer** | Active declare (creates queue if absent, passes `arguments`) | Passive declare (`passive=True`) — raises if queue is missing |
| **Consumer** | Active declare with `durable` + `arguments` | Active declare, always `durable=True`, no extra arguments |
| **Queue type** | Supported (via `queue_type` / `x-queue-type`) | Not supported (broker default) |
| **Dead-letter** | Supported | Not supported |
| **Where to define** | In a shared `queues.py` module | Inline wherever convenient |

Define `QueueConfig` instances in one place (e.g. `myapp/queues.py`) and import them in producers, consumers, and setup functions to keep the queue name and settings in sync.

## Setup Functions

A setup function is any callable that accepts a single `BlockingChannel` argument and uses it to declare exchanges, queues, and bindings:

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

**All setup functions must be idempotent.** RabbitMQ `exchange_declare` and `queue_declare` are safe to call multiple times with the same parameters — the broker ignores a re-declaration of an already-present object with identical settings. Calling `setup_rabbitmq_topology` twice must not raise.

## Registering Setup Functions

Register your setup functions inside `AppConfig.ready()` so that they are collected before `setup_rabbitmq_topology` is invoked:

```python
from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = 'orders'

    def ready(self) -> None:
        from django_rmq.registries.setup_registry import get_setup_registry

        from orders.topology import setup_orders_topology

        get_setup_registry().register(fn=setup_orders_topology)
```

For a multi-alias setup, pass `using` to `get_setup_registry`:

```python
get_setup_registry(using='payments').register(fn=setup_payments_topology)
```

## Running the Setup Command

```bash
uv run python manage.py setup_rabbitmq_topology
```

With an explicit alias:

```bash
uv run python manage.py setup_rabbitmq_topology --using payments
```

The command opens one channel per connection alias, calls every registered setup function in registration order, then closes the channel. It reports each declared object. Because all declarations are idempotent you can run this command safely in CI/CD pipelines and deployment scripts.

See [Management Commands](/en/1.0.5/management-commands.html) for the full command reference.

## Dead-Letter Topology Example

A dead-letter topology requires three components:

1. A dead-letter exchange (DLX).
2. A dead-letter queue (DLQ) bound to the DLX.
3. A main queue declared with `x-dead-letter-exchange` pointing at the DLX.

The following example mirrors the integration test in `tests/integration/test_dlx.py`:

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

After running `setup_rabbitmq_topology`, any message that causes `handle_order` to raise will be nacked without requeue and the broker will route it to `dlq-orders` via `dlx-orders`.

## See Also

- [Producers](/en/1.0.5/producers.html) — how `QueueConfig` affects queue declaration in the producer.
- [Consumers](/en/1.0.5/consumers.html) — how `QueueConfig` affects queue declaration in the consumer.
- [Registries](/en/1.0.5/registries.html) — `SetupRegistry` lifecycle and `get_setup_registry`.
- [Management Commands](/en/1.0.5/management-commands.html) — `setup_rabbitmq_topology` reference.
- [Reliability](/en/1.0.5/reliability.html) — dead-letter delivery guarantees.
- [API Reference](/en/1.0.5/api-reference.html) — `QueueConfig` and `SetupRegistry` signatures.
