# Changelog

All notable changes to **Django-RMQ** are documented in this file.

## [1.0.1] — 2026-07-05

First production-ready release of Django-RMQ — a set of Django wrappers and tools
for RabbitMQ built on top of [Pika](https://pika.readthedocs.io/).

### Core

- **Producer** (`django_rmq.producer`) — publish messages to RabbitMQ with
  publisher confirms and reconnection handling.
- **Consumer** (`django_rmq.consumer`) — long-running message consumers with
  acknowledgement control and graceful shutdown.
- **Connection manager** (`RabbitMQConnectionManager`) — centralized connection
  lifecycle management over Pika.
- **Registries** — `ConsumersRegistry` and `SetupRegistry` for declaratively
  registering consumers and topology setup routines.
- **Multiple connections** — run producers/consumers against several RabbitMQ
  brokers from a single project.

### Management commands

- `setup_rabbitmq_topology` — declaratively create exchanges, queues, and
  bindings from your configuration (replaces the earlier `setup_rabbitmq`).
- `start_consumers` — boot registered consumers as a manageable process.
- Styled command output ("mega-RDD" formatting) with shared `base_rdd_command`
  base class and ASCII-art banners.

### Typing

- The package ships `py.typed` and is a **PEP 561 typed package** — downstream
  code gets full type information.
- Strict type checking with **pyrefly** (`preset = "strict"`); all typing issues
  across the codebase resolved.
- Bundled `pika-stubs` so Pika calls are typed out of the box.

### Tooling & CI

- **Ruff** adopted for linting and formatting.
- **Unit and integration test suites** (`pytest`, `pytest-django`,
  `pytest-cov`); integration tests run against a real broker and are deselected
  by default via the `integration` marker.
- GitHub Actions workflows for testing, linting, and PyPI publishing on release.

### Documentation

- Full **VuePress documentation portal** in English and Russian:
  getting started, configuration, producers, consumers, registries, topology,
  reliability, multiple connections, management commands, testing, and a
  complete API reference.
- Expanded `README.md` with project logo and badges.

### Compatibility

- Supports **Python 3.10–3.14** and **Django 4.2 / 5.0 / 5.1 / 5.2 / 6.0**.
- Requires `pika>=1.4.1,<2.0`.

[1.0.1]: https://github.com/RDDLab/Django-RMQ/releases/tag/v1.0.1
