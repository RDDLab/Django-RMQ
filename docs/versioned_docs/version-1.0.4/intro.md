---
title: Django-RMQ General
sidebar_label: Home
slug: /
sidebar_position: 1
---

## What is Django-RMQ in a nutshell

Django-RMQ provides RabbitMQ wrappers and tools for Django projects using Pika.

It is not a full task queue or a Celery replacement. It is a lightweight integration layer for projects that want to publish messages, consume messages, and keep RabbitMQ infrastructure code tidy inside a Django application.

## Feature overview

- [Configuration](./configuration.md) — `RABBITMQ_CONNECTIONS` in `settings.py`; one entry per broker alias.
- [Producers](./producers.md) — publish messages, decorator mode, persistent delivery, publisher confirms.
- [Consumers](./consumers.md) — register handlers, explicit ack/nack, exponential reconnect backoff.
- [Topology](./topology.md) — `QueueConfig`, setup functions, dead-letter routing.
- [Registries](./registries.md) — `ConsumersRegistry` and `SetupRegistry` per alias.
- [Management commands](./management-commands.md) — `setup_rabbitmq_topology` and `start_consumers`.
- [Reliability](./reliability.md) — at-least-once delivery, mandatory routing, producer self-heal, DLX.
- [Multiple connections](./multiple-connections.md) — several broker aliases with the `using=` parameter.
- [API Reference](./api-reference.md) — full signatures and parameter docs for every public symbol.
- [Testing](./testing.md) — unit tests with mocked Pika; integration tests against a real broker.

## Installation

Install the package:

```bash
pip install django-rmq
```

Add `'django_rmq'` to `INSTALLED_APPS` and add a `RABBITMQ_CONNECTIONS` block to `settings.py`. See the [Getting Started](./getting-started.md) guide for the full minimal setup.

## Testing

See the [Testing](./testing.md) page for how to run the unit and integration test suites.
