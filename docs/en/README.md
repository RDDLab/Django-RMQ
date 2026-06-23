---
title: Django-RMQ General
home: true
heroImage: /logo.svg
heroAlt: Django-RMQ
heroText: false
tagline: Django RabbitMQ Wrappers & Tools over Pika
actions:
  - text: Get Started
    link: /en/#installation
    type: primary
  - text: Introduction
    link: /en/#what-is-django-rmq-in-a-nutshell
    type: secondary
highlights:
  - features:
      - title: Production ready
        details: Django-RMQ is designed for Django projects that need predictable RabbitMQ integration in real applications.
      - title: Django native
        details: Keep RabbitMQ connection settings and messaging code close to your Django project configuration.
      - title: Easily extensible
        details: Build producers and consumers around small wrappers instead of spreading Pika boilerplate across the codebase.
      - title: Strongly typed
        details: Django-RMQ ships typing support, so editors and type checkers can help while you work with messaging code.
---

## What is Django-RMQ in a nutshell

Django-RMQ provides RabbitMQ wrappers and tools for Django projects using Pika.

It is not a full task queue or a Celery replacement. It is a lightweight integration layer for projects that want to publish messages, consume messages, and keep RabbitMQ infrastructure code tidy inside a Django application.

## Installation

You can install Django-RMQ with pip or your favorite Python dependency manager:

```bash
pip install django-rmq
```

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
