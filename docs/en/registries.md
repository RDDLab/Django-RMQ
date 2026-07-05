---
title: Registries
order: 7
---

# Registries

Registries are in-memory collections that the library uses to track, per connection alias, which consumers should run and which topology setup functions should be executed. They are created automatically by `RabbitMQAppConfig.ready()` — one of each per configured alias.

There are two registry types:

- **`ConsumersRegistry`** — holds `Consumer` instances; used by `start_consumers`.
- **`SetupRegistry`** — holds `SetupFn` callables; used by `setup_rabbitmq_topology`.

## ConsumersRegistry

`ConsumersRegistry` stores the consumers that the `start_consumers` management command will launch.

```python
from django_rmq.registries.registry import ConsumersRegistry, get_consumers_registry
```

### API

| Method / Function | Signature | Description |
|-------------------|-----------|-------------|
| `register` | `(consumer: Consumer) -> None` | Appends a consumer to the registry. |
| `all` | `() -> list[Consumer]` | Returns a copy of the registered consumers list. |
| `get_consumers_registry` | `(using: str \| None = None) -> ConsumersRegistry` | Module-level helper that resolves the registry for the given alias. |

`all()` always returns a new list, so the caller cannot mutate the internal registry state.

### Registering a consumer

Define the consumer and its handler in a dedicated module — for example, `orders/consumers.py`:

```python
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

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
    # process the message
    channel.basic_ack(delivery_tag=method.delivery_tag)
```

Then register it in the `ready()` method of one of your application's `AppConfig` classes, after `django_rmq` has been initialized:

```python
from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = 'orders'

    def ready(self) -> None:
        from django_rmq.registries.registry import get_consumers_registry

        from orders.consumers import consumer

        get_consumers_registry().register(consumer=consumer)
```

### Per-alias usage

When multiple connections are configured, pass `using` to target the right registry:

```python
from django_rmq.consumer import Consumer
from django_rmq.registries.registry import get_consumers_registry

analytics_consumer: Consumer = Consumer(queue='events', using='analytics')
get_consumers_registry(using='analytics').register(consumer=analytics_consumer)
```

## SetupRegistry

`SetupRegistry` stores `SetupFn` callables — functions that declare exchanges, queues, and bindings on the broker. The `setup_rabbitmq_topology` command opens a channel per alias and calls `run_all` to execute every registered function.

```python
from django_rmq.registries.setup_registry import SetupRegistry, SetupFn, get_setup_registry
```

### `SetupFn` type alias

```python
from collections.abc import Callable
from pika.adapters.blocking_connection import BlockingChannel

SetupFn = Callable[[BlockingChannel], None]
```

A `SetupFn` receives an open `BlockingChannel` and must be **idempotent** — RabbitMQ's topology declarations are passive-safe, so re-running the same function on a repeat deploy does not raise errors.

### API

| Method / Function | Signature | Description |
|-------------------|-----------|-------------|
| `register` | `(fn: SetupFn) -> None` | Appends a setup function to the registry. |
| `run_all` | `(channel: BlockingChannel) -> None` | Calls every registered function in registration order. |
| `get_setup_registry` | `(using: str \| None = None) -> SetupRegistry` | Module-level helper that resolves the registry for the given alias. |

Functions are called in the order they were registered.

### Registering a setup function

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

### Per-alias usage

```python
from pika.adapters.blocking_connection import BlockingChannel

from django_rmq.registries.setup_registry import get_setup_registry


def setup_analytics(channel: BlockingChannel) -> None:
    channel.queue_declare(queue='events', durable=True)


get_setup_registry(using='analytics').register(fn=setup_analytics)
```

## Per-alias resolution

Both `get_consumers_registry` and `get_setup_registry` delegate to `resolve_alias` internally:

- When exactly one alias is configured, `using` may be omitted.
- When multiple aliases are configured, `using` is required; omitting it raises `ImproperlyConfigured`.
- Passing an unknown alias raises `ImproperlyConfigured`.

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

## Lifecycle

Registries are created empty by `RabbitMQAppConfig.ready()` at Django startup. They are populated during the same startup phase when your `AppConfig.ready()` methods run. After startup the registries are read-only from the library's perspective — `start_consumers` and `setup_rabbitmq_topology` only call `all()` and `run_all()`, never mutate the lists.

Registering a consumer or setup function after Django has started (e.g. inside a view) works mechanically but means those entries will not be picked up by the management commands in the current process if the command was already running.
