# Changelog

All notable changes to **Django-RMQ** are documented in this file.

## [1.0.4] — Unreleased

### Fixed

- **Consumer** — guard `basic_nack` against a missing delivery tag: when a
  handler raises, the message is only nacked if `method.delivery_tag` is set,
  avoiding an invalid nack with `delivery_tag=None`.

### Changed

- **Topology setup** — the `RecordingChannel` proxy used by
  `setup_rabbitmq_topology` now exposes explicit, fully typed keyword parameters
  (`passive`, `durable`, `auto_delete`, `internal`, `exclusive`, `arguments`, …)
  on `exchange_declare` / `queue_declare` / `queue_bind`, mirroring Pika's
  `BlockingChannel` instead of accepting `**kwargs`. Setup functions get proper
  type checking and the overrides are now LSP-consistent.

[1.0.4]: https://github.com/RDDLab/Django-RMQ/releases/tag/1.0.4

## [1.0.3] — 2026-07-08

### Management commands

- `check_rabbitmq_connections` — healthcheck command that verifies RabbitMQ
  connectivity by opening and immediately closing a connection per alias. Pass
  `--using <alias>` to check a single connection, or omit it to check every
  alias in `RABBITMQ_CONNECTIONS`. Reports each alias as OK/FAIL and exits with
  a `CommandError` if any connection is unreachable.

### Documentation

- Documented `check_rabbitmq_connections` in the English and Russian
  management-commands guides.

[1.0.3]: https://github.com/RDDLab/Django-RMQ/releases/tag/1.0.3

## [1.0.2] — 2026-07-05

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

[1.0.2]: https://github.com/RDDLab/Django-RMQ/releases/tag/1.0.2
