---
title: Configuration
order: 3
---

# Configuration

## Register the application

Add `'django_rmq'` to `INSTALLED_APPS` in your Django settings:

```python
INSTALLED_APPS: list[str] = [
    # ...
    'django_rmq',
]
```

When Django starts, `RabbitMQAppConfig.ready()` reads `RABBITMQ_CONNECTIONS` and builds, for every alias, a
`RabbitMQConnectionManager`, a `SetupRegistry`, and a `ConsumersRegistry`. These are stored as module-level attributes
on `django_rmq` and are available from that point on.

If `RABBITMQ_CONNECTIONS` is missing or empty when `ready()` runs, Django raises `ImproperlyConfigured` and refuses to
start.

## `RABBITMQ_CONNECTIONS`

`RABBITMQ_CONNECTIONS` is a `dict` that maps an alias name to a connection parameters dict. All nine keys are required
for every alias.

```python
RABBITMQ_CONNECTIONS: dict[str, dict[str, object]] = {
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

### Parameter reference

| Key                          | Type    | `RabbitMQConfig` field       | Description                                                            |
|------------------------------|---------|------------------------------|------------------------------------------------------------------------|
| `HOST`                       | `str`   | `host`                       | Broker hostname or IP address.                                         |
| `PORT`                       | `int`   | `port`                       | Broker AMQP port (typically `5672`).                                   |
| `VIRTUAL_HOST`               | `str`   | `virtual_host`               | AMQP virtual host to connect to.                                       |
| `USER`                       | `str`   | `user`                       | Username for PlainCredentials authentication.                          |
| `PASSWORD`                   | `str`   | `password`                   | Password for PlainCredentials authentication.                          |
| `HEARTBEAT`                  | `int`   | `heartbeat`                  | Heartbeat interval in seconds negotiated with the broker.              |
| `BLOCKED_CONNECTION_TIMEOUT` | `int`   | `blocked_connection_timeout` | Seconds to wait while the broker blocks the connection before failing. |
| `RECONNECT_INITIAL_BACKOFF`  | `float` | `reconnect_initial_backoff`  | Initial consumer reconnect delay in seconds.                           |
| `RECONNECT_MAX_BACKOFF`      | `float` | `reconnect_max_backoff`      | Maximum consumer reconnect delay (cap for exponential backoff).        |

`RabbitMQConfig` is a frozen dataclass. After `ready()` completes each alias has its own immutable config instance;
modifying the settings dict at runtime has no effect.

## Single connection vs multiple connections

When exactly one alias is defined you may omit the `using` parameter on `Producer`, `Consumer`, and the management
commands — the single alias is resolved automatically.

When two or more aliases are defined you must pass `using='<alias>'` explicitly. Omitting it raises
`ImproperlyConfigured` with a message listing the configured aliases.

Single alias:

```python
from django_rmq.producer import Producer

producer: Producer = Producer(queue='orders')
producer.publish(body='{"id": 1}')
```

Multiple aliases — `using` required:

```python
from django_rmq.producer import Producer

orders_producer: Producer = Producer(queue='orders', using='default')
analytics_producer: Producer = Producer(queue='events', using='analytics')
```

See [Multiple Connections](/en/multiple-connections.html) for a complete multi-alias example.

## Error cases

| Situation                               | Exception              | Message                                                                          |
|-----------------------------------------|------------------------|----------------------------------------------------------------------------------|
| `RABBITMQ_CONNECTIONS` missing or empty | `ImproperlyConfigured` | `django_rmq requires RABBITMQ_CONNECTIONS …`                                     |
| `'django_rmq'` not in `INSTALLED_APPS`  | `ImproperlyConfigured` | `django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.`             |
| `using` omitted with multiple aliases   | `ImproperlyConfigured` | `Multiple RabbitMQ connections configured (…); pass using='<alias>' explicitly.` |
| `using` set to an unknown alias         | `ImproperlyConfigured` | `Unknown RabbitMQ alias '<alias>'.`                                              |

## Reading credentials from environment variables

Storing credentials directly in settings files is not recommended for production. A common approach is to read them from
environment variables:

```python
import os
from typing import Any

RABBITMQ_CONNECTIONS: dict[str, dict[str, Any]] = {
    'default': {
        'HOST': os.environ.get('RMQ_HOST', 'localhost'),
        'PORT': int(os.environ.get('RMQ_PORT', '5672')),
        'VIRTUAL_HOST': os.environ.get('RMQ_VIRTUAL_HOST', '/'),
        'USER': os.environ.get('RMQ_USER', 'guest'),
        'PASSWORD': os.environ.get('RMQ_PASSWORD', 'guest'),
        'HEARTBEAT': int(os.environ.get('RMQ_HEARTBEAT', '600')),
        'BLOCKED_CONNECTION_TIMEOUT': int(os.environ.get('RMQ_BLOCKED_CONNECTION_TIMEOUT', '300')),
        'RECONNECT_INITIAL_BACKOFF': float(os.environ.get('RMQ_RECONNECT_INITIAL_BACKOFF', '1.0')),
        'RECONNECT_MAX_BACKOFF': float(os.environ.get('RMQ_RECONNECT_MAX_BACKOFF', '30.0')),
    },
}
```

You can also use `django-environ`, `python-decouple`, or any other env-loading library — `RABBITMQ_CONNECTIONS` is a
plain Python dict, so any value source works.
