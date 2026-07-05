---
title: Multiple Connections
order: 10
---

# Multiple Connections

Django-RMQ supports any number of RabbitMQ connections in a single Django project.
Each connection is identified by an **alias** key in `RABBITMQ_CONNECTIONS`. The
`using` parameter on `Producer`, `Consumer`, and the accessor functions selects
which connection to use.

---

## Configuring multiple aliases

Add one entry per broker (or per virtual host) to `RABBITMQ_CONNECTIONS`:

```python
# settings.py
RABBITMQ_CONNECTIONS: dict = {
    'default': {
        'HOST': 'rmq-primary.internal',
        'PORT': 5672,
        'VIRTUAL_HOST': '/',
        'USER': 'app',
        'PASSWORD': 'secret',
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    },
    'analytics': {
        'HOST': 'rmq-analytics.internal',
        'PORT': 5672,
        'VIRTUAL_HOST': '/analytics',
        'USER': 'analytics_user',
        'PASSWORD': 'secret',
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    },
}
```

On `AppConfig.ready()`, Django-RMQ creates an independent
`RabbitMQConnectionManager`, `ConsumersRegistry`, and `SetupRegistry` for every
alias. These objects are stored in the `django_rmq` module under
`connection_managers`, `consumers_registries`, and `setup_registries`.

---

## The `using` parameter

`Producer`, `Consumer`, `get_connection_manager`, `get_consumers_registry`, and
`get_setup_registry` all accept an optional `using` keyword argument:

```python
from django_rmq.producer import Producer
from django_rmq.consumer import Consumer
from django_rmq.queues.queue_config import QueueConfig

# Publishes to the 'analytics' broker.
analytics_producer: Producer = Producer(
    queue='page-views',
    using='analytics',
)

# Consumes from the 'default' broker.
order_consumer: Consumer = Consumer(
    queue=QueueConfig(name='orders'),
    using='default',
)
```

---

## Resolution rules

The `using` parameter is resolved by `resolve_alias` in `django_rmq/utils.py`:

| Situation                                       | Result                           |
|-------------------------------------------------|----------------------------------|
| `using` omitted, exactly one alias configured   | That alias is used automatically |
| `using` omitted, more than one alias configured | `ImproperlyConfigured` is raised |
| `using` provided and matches an alias           | That alias is used               |
| `using` provided but unknown                    | `ImproperlyConfigured` is raised |
| `django_rmq` not in `INSTALLED_APPS`            | `ImproperlyConfigured` is raised |

When you have a single alias, omitting `using` everywhere is safe and recommended.
Once you add a second alias, every `Producer`, `Consumer`, and registry accessor
must specify `using` explicitly to avoid the ambiguity error.

---

## Registering consumers and setup functions per alias

Both `get_consumers_registry` and `get_setup_registry` accept `using`:

```python
# myapp/apps.py
from django.apps import AppConfig
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType

from django_rmq.consumer import Consumer
from django_rmq.queues.queue_config import QueueConfig
from django_rmq.registries.registry import get_consumers_registry
from django_rmq.registries.setup_registry import get_setup_registry


class MyAppConfig(AppConfig):
    name = 'myapp'

    def ready(self) -> None:
        from myapp.consumers import order_consumer, analytics_consumer

        get_consumers_registry(using='default').register(consumer=order_consumer)
        get_consumers_registry(using='analytics').register(consumer=analytics_consumer)

        def setup_analytics(channel: BlockingChannel) -> None:
            channel.exchange_declare(
                exchange='events',
                exchange_type=ExchangeType.topic,
                durable=True,
            )
            channel.queue_declare(queue='page-views', durable=True)
            channel.queue_bind(
                queue='page-views',
                exchange='events',
                routing_key='page.*',
            )

        get_setup_registry(using='analytics').register(fn=setup_analytics)
```

---

## Per-alias management commands

Both management commands accept `--using` to target a single alias. Without it
they run for every configured alias.

```bash
# Declare topology for the 'analytics' alias only.
uv run python manage.py setup_rabbitmq_topology --using analytics

# Start consumers for the 'default' alias only.
uv run python manage.py start_consumers --using default

# Run for all aliases (omit --using).
uv run python manage.py setup_rabbitmq_topology
uv run python manage.py start_consumers
```

---

## Full example

The example below sets up two independent consumers on two different brokers and
verifies that their registries are separate objects:

```python
# tests/test_registries.py (adapted)
from django_rmq.registries.registry import get_consumers_registry
from django_rmq.registries.setup_registry import get_setup_registry

# After configuring two aliases:
default_consumers = get_consumers_registry(using='default')
analytics_consumers = get_consumers_registry(using='analytics')
default_setup = get_setup_registry(using='default')
analytics_setup = get_setup_registry(using='analytics')

assert default_consumers is not analytics_consumers
assert default_setup is not analytics_setup
```

A complete two-alias settings example (with env-var injection for production):

```python
# settings.py
import os

RABBITMQ_CONNECTIONS: dict = {
    'default': {
        'HOST': os.environ.get('RMQ_DEFAULT_HOST', 'localhost'),
        'PORT': int(os.environ.get('RMQ_DEFAULT_PORT', '5672')),
        'VIRTUAL_HOST': os.environ.get('RMQ_DEFAULT_VHOST', '/'),
        'USER': os.environ.get('RMQ_DEFAULT_USER', 'guest'),
        'PASSWORD': os.environ.get('RMQ_DEFAULT_PASSWORD', 'guest'),
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    },
    'analytics': {
        'HOST': os.environ.get('RMQ_ANALYTICS_HOST', 'localhost'),
        'PORT': int(os.environ.get('RMQ_ANALYTICS_PORT', '5672')),
        'VIRTUAL_HOST': os.environ.get('RMQ_ANALYTICS_VHOST', '/analytics'),
        'USER': os.environ.get('RMQ_ANALYTICS_USER', 'guest'),
        'PASSWORD': os.environ.get('RMQ_ANALYTICS_PASSWORD', 'guest'),
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    },
}
```

For the full list of required configuration keys see
[Configuration](/en/configuration.html).
