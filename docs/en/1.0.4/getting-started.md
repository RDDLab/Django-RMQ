---
title: Getting Started
order: 2
---

# Getting Started

## Requirements

- Python >= 3.10
- Django >= 4.2
- RabbitMQ 3.13–4.3
- `pika==1.4.1` (installed automatically as a dependency)

## Installation

```bash
pip install django-rmq
```

## Register the app

Add `'django_rmq'` to `INSTALLED_APPS` in your `settings.py`:

```python
INSTALLED_APPS = [
    # ...
    'django_rmq',
]
```

`RabbitMQAppConfig.ready()` reads `RABBITMQ_CONNECTIONS` on startup and initializes connection managers and registries
per alias. The setting must be present and non-empty, or Django will raise `ImproperlyConfigured` during startup.

## Minimal settings

Add a `RABBITMQ_CONNECTIONS` block with at least one alias. All nine keys are required:

```python
RABBITMQ_CONNECTIONS = {
    'default': {
        'HOST': 'localhost',
        'PORT': 5672,
        'VIRTUAL_HOST': '/',
        'USER': 'guest',
        'PASSWORD': 'guest',
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    },
}
```

See [Configuration](/en/1.0.4/configuration.html) for the full parameter reference and how to read values from environment
variables.

## Publish your first message

Create a `Producer` and call `publish`. The queue is declared lazily on the first publish call:

```python
from django_rmq.producer import Producer

Producer(queue='orders').publish(body='{"order_id": 42}')
```

- `body` accepts `str` or `bytes`. Strings are UTF-8-encoded automatically.
- Every message is published with `delivery_mode=2` (persistent) and `mandatory=True` by default.

See [Producers](/en/1.0.4/producers.html) for routing keys, custom properties, exchange-only mode, and the decorator style.

## Consume your first message

### 1. Create and register a consumer

Create a `Consumer`, register a handler function, and add the consumer to the registry. A good place for this code is a
dedicated `consumers.py` module inside your Django app or even dedicated `consumers` app:

```python
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic,
    BasicProperties

from django_rmq.consumer import Consumer
from django_rmq.registries.registry import get_consumers_registry

consumer: Consumer = Consumer(queue='orders')


@consumer
def handle_order(
    ch: BlockingChannel,
    method: Basic.Deliver,
    props: BasicProperties,
    body: bytes,
) -> None:
    # process the message ...
    ch.basic_ack(delivery_tag=method.delivery_tag)


get_consumers_registry().register(consumer=consumer)
```

The library does **not** auto-ack messages on success. Every handler must call `ch.basic_ack(...)` or
`ch.basic_nack(...)` explicitly. If the handler raises an unhandled exception, the consumer calls
`ch.basic_nack(requeue=False)` automatically so the message goes to the dead-letter exchange (if configured) instead of
looping forever.

### 2. Import the consumers module in AppConfig.ready()

Django imports app modules lazily, so the `consumers.py` module must be imported explicitly to register the consumer
before `start_consumers` runs. Override `ready()` in your app's `AppConfig`:

```python
from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = 'orders'

    def ready(self) -> None:
        import orders.consumers  # noqa: F401
```

### 3. Start the consumer runner

```bash
uv run python manage.py start_consumers
```

The command starts one thread per registered consumer, prints a summary table, and handles graceful shutdown on
`SIGTERM`/`SIGINT`.

## Where to keep consumers

Keep consumer definitions in a `consumers.py` file (or a `consumers/` package) at the root of each Django app that owns
the queue. Import that module in the app's `AppConfig.ready()`.

## Next steps

| Topic                                                           | Page                                                  |
|-----------------------------------------------------------------|-------------------------------------------------------|
| Full configuration reference                                    | [Configuration](/en/1.0.4/configuration.html)               |
| Producers — decorator mode, exchange routing, custom properties | [Producers](/en/1.0.4/producers.html)                       |
| Consumers — reconnect behavior, DLX, prefetch                   | [Consumers](/en/1.0.4/consumers.html)                       |
| Declaring exchanges, queues, and bindings                       | [Topology](/en/1.0.4/topology.html)                         |
| Registries and the AppConfig lifecycle                          | [Registries](/en/1.0.4/registries.html)                     |
| Management commands                                             | [Management Commands](/en/1.0.4/management-commands.html)   |
| Reliability guarantees                                          | [Reliability](/en/1.0.4/reliability.html)                   |
| Multiple broker connections                                     | [Multiple Connections](/en/1.0.4/multiple-connections.html) |
| Full public API                                                 | [API Reference](/en/1.0.4/api-reference.html)               |
| Running and writing tests                                       | [Testing](/en/1.0.4/testing.html)                           |
