# Changelog

All notable changes to **Django-RMQ** are documented in this file.

## [1.0.5] — Unreleased

### Added

- **RabbitMQ cluster support** — an alias can now define multiple broker nodes via the new NODES key (list of {HOST,
  PORT}); pika iterates the nodes for client-side failover. Credentials, virtual host, and timeouts are shared across
  nodes. The legacy scalar HOST/PORT form still works and is treated as a single node.
- **SHUFFLE_NODES** (optional, default False) — reshuffles the node order on every connection attempt so clients spread
  across the cluster.
- **Queue type support** — `QueueConfig` gained a new optional `queue_type` field, backed by a new `QueueType` enum
  (`classic`/`quorum`/`stream`, in `django_rmq/queues/queue_config.py`). It sets the `x-queue-type` declaration
  argument; when left as `None` (the default), the broker applies its own `default_queue_type`. Fully backward
  compatible — no producer or consumer changes required.

### Tests

- **Cluster integration tests** — a committed three-node RabbitMQ cluster (`.github/docker-compose.cluster.yml`,
  classic_config peer discovery, shared Erlang cookie, `default_queue_type = quorum`) backs a new
  `tests/integration/test_cluster.py` suite, marked with the new `cluster` marker (run via `pytest -m cluster`). Covers
  a dead node being skipped in the `NODES` list, `SHUFFLE_NODES` spreading connections across nodes, and the headline
  scenario — a producer/consumer failing over to a surviving node after `docker kill` takes down the one they were
  connected to. Cluster tests auto-skip (`require_cluster`) when fewer than two nodes are reachable, so a single-broker
  environment is unaffected. CI runs them in a new dedicated `cluster-test` job; the existing integration job now runs
  `pytest -m "integration and not cluster"`.

### Changed

- **Configuration validation** — NODES and HOST/PORT are mutually exclusive; empty NODES, a node missing HOST/PORT, or
  specifying neither form now raises ImproperlyConfigured (see django_rmq/apps.py._resolve_nodes).

### Documentation

- New "Clusters" guide (EN/RU) covering client-side failover, NODES vs load balancer/DNS, SHUFFLE_NODES, reconnect
  interaction, and quorum queues. Configuration guide updated with NODES/SHUFFLE_NODES and the new validation error
  cases.
- Testing guide (EN/RU) documents the cluster integration tests — how to bring up the three-node cluster, run
  `pytest -m cluster`, and what each test covers. Clusters guide links to it.
- API reference, Topology, and Clusters guides (EN/RU) updated for `queue_type` / `QueueType`. The Clusters guide's
  "Quorum queues" section is rewritten to recommend declaring quorum queues via
  `QueueConfig(queue_type=QueueType.QUORUM)`, with the raw setup-function approach kept as a lower-level alternative.
- **Documentation versioning** — the VuePress site now serves versioned docs under `/{en,ru}/1.0.5/` (current) and
  `/{en,ru}/1.0.4/` (frozen snapshot from the `1.0.4` tag). `/en/` and `/ru/` redirect to the latest version, and a
  "Version" dropdown in the navbar switches between them. The 1.0.4 sidebar omits the Clusters guide, which did not
  exist in that release.

## [1.0.4] — 2026-07-11

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
