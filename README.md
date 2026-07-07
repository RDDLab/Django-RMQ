![Logo](https://github.com/RDDLab/Django-RMQ/raw/main/docs/.vuepress/public/logo.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=for-the-badge)](https://docs.astral.sh/ruff)
[![pyrefly](https://img.shields.io/endpoint?url=https://pyrefly.org/badge.json&style=for-the-badge)](https://pyrefly.org)
[![PyPI](https://img.shields.io/pypi/v/django-rmq?style=for-the-badge)](https://pypi.org/project/django-rmq/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/django-rmq.svg?style=for-the-badge)](https://pypi.python.org/pypi/django-rmq/)
[![PyPI djversions](https://img.shields.io/pypi/djversions/django-rmq.svg?style=for-the-badge)](https://pypi.org/project/django-rmq/)
[![PyPI status](https://img.shields.io/pypi/status/django-rmq.svg?style=for-the-badge)](https://pypi.python.org/pypi/django-rmq)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/django-rmq?style=for-the-badge)](https://pypistats.org/packages/django-rmq)
[![PyPI - Types](https://img.shields.io/pypi/types/django-rmq.svg?style=for-the-badge)](https://pypi.python.org/pypi/django-rmq)
---

[![RabbitMQ Support](https://img.shields.io/static/v1?label=RabbitMQ%20Support&message=v3.13%20%7C%20v4.0%20%7C%20v4.1%20%7C%20v4.2%20%7C%20v4.3&color=ff6600&labelColor=555&style=for-the-badge)](https://www.rabbitmq.com/)

---
[![Tests](https://img.shields.io/github/actions/workflow/status/RDDLab/Django-RMQ/testing.yml?branch=main&label=Tests)](https://github.com/RDDLab/Django-RMQ/actions/workflows/testing.yml)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13524/badge)](https://www.bestpractices.dev/projects/13524)
[![Codecov](https://img.shields.io/codecov/c/github/RDDLab/Django-RMQ/main?logo=codecov)](https://codecov.io/gh/RDDLab/Django-RMQ)
---

**Documentation**: <a href="https://django-rmq.rdd-lab.com/" target="_blank">https://django-rmq.rdd-lab.com/</a>

**Source Code**: <a href="https://github.com/RDDLab/Django-RMQ" target="_blank">https://github.com/RDDLab/Django-RMQ</a>

---

# Django-RMQ

Django-RMQ provides RabbitMQ wrappers and tools for Django projects, built on top of [Pika](https://pika.readthedocs.io/). It is a lightweight integration layer — not a task queue or a Celery replacement — for projects that need to publish and consume messages while keeping broker infrastructure code predictable and close to the Django configuration. Supports RabbitMQ 3.13–4.3.

## Features

- **Django-native settings** — configure broker connections via `RABBITMQ_CONNECTIONS` in `settings.py`, one entry per alias.
- **`Producer` and `Consumer` wrappers** — thin classes over Pika's blocking connection that handle channel lifecycle and lazy queue declaration.
- **Decorator-style publishing** — use a `Producer` instance as a `@producer` decorator to auto-publish a function's return value.
- **Reliable delivery** — publisher confirms, `mandatory=True`, and `delivery_mode=2` (persistent) are enforced on every message.
- **Auto-reconnect with backoff** — producers retry once on transient channel errors; consumers reconnect with exponential backoff capped at a configurable maximum.
- **Dead-letter routing** — declare queues with `QueueConfig(dead_letter_exchange=...)` so unhandled messages are nacked without requeue and routed to a DLX.
- **Management commands** — `setup_rabbitmq_topology` (idempotent exchange/queue/binding setup) and `start_consumers` (threaded runner with graceful SIGTERM/SIGINT shutdown).
- **Multiple connections** — configure several broker aliases and select per producer/consumer via `using=`.
- **Fully typed** — ships `py.typed`; compatible with pyrefly and standard type checkers.

## Installation

```bash
pip install django-rmq
```

Add `'django_rmq'` to `INSTALLED_APPS` and configure at least one connection alias:

```python
INSTALLED_APPS = [
    # ...
    'django_rmq',
]

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

## Quick start

**Publish a message:**

```python
from django_rmq.producer import Producer

Producer(queue='orders').publish(body='{"order_id": 42}')
```

**Consume messages** (e.g. `myapp/consumers.py`):

```python
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

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
    print(body)
    ch.basic_ack(delivery_tag=method.delivery_tag)


get_consumers_registry().register(consumer=consumer)
```

Import `consumers.py` inside your app's `AppConfig.ready()`, then start consuming:

```bash
uv run python manage.py start_consumers
```

## Documentation

Full reference, configuration guide, reliability details, and more:

**https://django-rmq.rdd-lab.com/**

---

## Testing

### Unit tests

Unit tests mock `pika` and need no broker. They run by default — integration
tests are marked `integration` and deselected:

```bash
uv run pytest
```

### Integration tests

Integration tests run against a **real** RabbitMQ broker. The repo ships a
`.github/docker-compose.yml` that starts the same image CI uses (with the
management plugin the suite needs on port `15672`). Connection params are read
from `RMQ_*` env vars (defaults: `localhost:5672`, `guest`/`guest`, vhost `/`),
which already match the Compose service:

```bash
docker compose -f .github/docker-compose.yml up -d --wait    # start the broker, block until healthy
uv run pytest -m integration
docker compose -f .github/docker-compose.yml down            # stop it when done
```

The suite isolates itself with per-test `uuid`-suffixed queues/exchanges and
cleans them up, so it is safe against a shared broker (use a dedicated vhost).

---

## License

MIT
