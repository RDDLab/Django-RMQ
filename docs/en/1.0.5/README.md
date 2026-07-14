---
title: Django-RMQ General
home: true
heroImage: /logo.svg
heroAlt: Django-RMQ
heroText: false
tagline: Django RabbitMQ Wrappers & Tools over Pika
actions:
  - text: Get Started
    link: /en/1.0.5/getting-started.html
    type: primary
  - text: Introduction
    link: /en/1.0.5/#what-is-django-rmq-in-a-nutshell
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

## Feature overview

- [Configuration](/en/1.0.5/configuration.html) — `RABBITMQ_CONNECTIONS` in `settings.py`; one entry per broker alias.
- [Producers](/en/1.0.5/producers.html) — publish messages, decorator mode, persistent delivery, publisher confirms.
- [Consumers](/en/1.0.5/consumers.html) — register handlers, explicit ack/nack, exponential reconnect backoff.
- [Topology](/en/1.0.5/topology.html) — `QueueConfig`, setup functions, dead-letter routing.
- [Registries](/en/1.0.5/registries.html) — `ConsumersRegistry` and `SetupRegistry` per alias.
- [Management commands](/en/1.0.5/management-commands.html) — `setup_rabbitmq_topology` and `start_consumers`.
- [Reliability](/en/1.0.5/reliability.html) — at-least-once delivery, mandatory routing, producer self-heal, DLX.
- [Multiple connections](/en/1.0.5/multiple-connections.html) — several broker aliases with the `using=` parameter.
- [API Reference](/en/1.0.5/api-reference.html) — full signatures and parameter docs for every public symbol.
- [Testing](/en/1.0.5/testing.html) — unit tests with mocked Pika; integration tests against a real broker.

## Installation

Install the package:

```bash
pip install django-rmq
```

Add `'django_rmq'` to `INSTALLED_APPS` and add a `RABBITMQ_CONNECTIONS` block to `settings.py`. See the [Getting Started](/en/1.0.5/getting-started.html) guide for the full minimal setup.

## Testing

See the [Testing](/en/1.0.5/testing.html) page for how to run the unit and integration test suites.
