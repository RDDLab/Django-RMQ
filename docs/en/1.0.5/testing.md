---
title: Testing
order: 12
---

# Testing

The test suite is split into **unit tests** (no broker required, pika is mocked)
and **integration tests** (require a live RabbitMQ broker). Both live under
`tests/`.

---

## Unit tests

Unit tests mock `pika.BlockingConnection` at the point `connections.py` imports
it, so no real broker is needed. They run by default because integration tests are
marked and deselected in `pyproject.toml`:

```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = '-ra -m "not integration"'
markers = [
    "integration: tests that require a real RabbitMQ broker (deselected by default)",
]
```

Run the unit suite:

```bash
uv run pytest
```

---

## Integration tests

Integration tests are marked with `pytest.mark.integration`. They require a
running RabbitMQ broker with the management plugin enabled (port `15672`).

The repository ships a Compose file that starts the same image CI uses:

```bash
# Start the broker and wait until healthy.
docker compose -f .github/docker-compose.yml up -d --wait

# Run only integration tests.
uv run pytest -m integration

# Stop the broker when done.
docker compose -f .github/docker-compose.yml down
```

### Environment variables

Connection parameters for integration tests are read from `RMQ_*` environment
variables. The defaults match the Compose service so no extra configuration is
needed for a local run:

| Variable | Default | Description |
|---|---|---|
| `RMQ_HOST` | `localhost` | Broker hostname |
| `RMQ_PORT` | `5672` | AMQP port |
| `RMQ_VHOST` | `/` | Virtual host |
| `RMQ_USER` | `guest` | Username |
| `RMQ_PASSWORD` | `guest` | Password |
| `RMQ_HEARTBEAT` | `30` | Heartbeat interval (seconds) |
| `RMQ_MGMT_PORT` | `15672` | Management API port |

Set them to point the suite at a different broker:

```bash
RMQ_HOST=rmq.staging.internal RMQ_USER=ci RMQ_PASSWORD=secret \
    uv run pytest -m integration
```

### Isolation

Every integration test receives collision-free, UUID-suffixed names for queues
and exchanges via the `names` fixture. All declared resources are deleted on
teardown so the suite is safe against a shared broker. Using a dedicated virtual
host is still recommended in CI.

---

## Cluster integration tests

A separate suite in `tests/integration/test_cluster.py` exercises **client-side
failover** against a real multi-node RabbitMQ cluster, rather than a single
broker. It proves the contract described in [Clusters](/en/1.0.5/clusters.html):
pika iterates the configured `NODES` sequence until one connects, and a client
survives the loss of the node it was on.

These tests are marked with `pytest.mark.cluster` in addition to
`pytest.mark.integration`:

```toml
# pyproject.toml
markers = [
    "integration: tests that require a real RabbitMQ broker (deselected by default)",
    "cluster: tests that require a multi-node RabbitMQ cluster (also marked integration)",
]
```

### Starting the cluster

The repository ships a dedicated three-node Compose file (classic_config peer
discovery, shared Erlang cookie, `default_queue_type = quorum`):

```bash
# Start the three-node cluster and wait until healthy.
docker compose -f .github/docker-compose.cluster.yml up -d --wait

# Run only the cluster tests.
uv run pytest -m cluster

# Stop the cluster and remove its containers.
docker compose -f .github/docker-compose.cluster.yml down -v
```

The cluster publishes AMQP on ports `5672`/`5673`/`5674` and the management API
on `15672`/`15673`/`15674` — the same ports used by `.github/docker-compose.yml`
for the single-broker setup.

If the cluster is not reachable, the `require_cluster` fixture skips the
cluster-only tests automatically (it checks that at least two of the three
nodes accept AMQP connections), so a single-broker environment does not fail
the run.

### What is covered

- `test_dead_node_in_list_is_skipped` — an unreachable node listed first in
  `NODES` is skipped by pika, and a publish/consume roundtrip completes on the
  live node. This test only needs one broker (marked `integration` only, not
  `cluster`), so it also runs in the regular single-broker integration job.
- `test_shuffle_spreads_connections_across_nodes` — with `SHUFFLE_NODES=True`,
  many independent connections land on more than one cluster node.
- `test_failover_after_node_down` — the headline scenario: a producer and
  consumer are connected to the first node, that node is killed via
  `docker kill` (the `node_control` fixture), and both fail over to a
  surviving node. The queue is quorum (the cluster's default), so it survives
  the node loss and the message still gets delivered.

The `node_control` fixture shells out to the `docker` CLI, so it (and
`test_failover_after_node_down`) requires Docker to be available on the
machine running the tests; it skips itself otherwise.

### CI

Cluster tests run in their own `cluster-test` job in
`.github/workflows/testing.yml`, which brings up
`.github/docker-compose.cluster.yml` and runs `pytest -m cluster`. The regular
`integration-test` job runs `pytest -m "integration and not cluster"` against a
single broker, so the two jobs never compete for the same ports.

---

## Testing your own producers and consumers

### Mocking pika in unit tests

The `patch_blocking_connection` fixture from `tests/conftest.py` replaces
`pika.BlockingConnection` with a `MagicMock`. Use it in your own test files by
importing and applying the same pattern:

```python
from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from django_rmq.connections import RabbitMQConnectionManager
from django_rmq.dto.rabbitmq_config import RabbitMQConfig


@pytest.fixture
def mock_channel() -> MagicMock:
    channel: MagicMock = MagicMock(name='BlockingChannel')
    channel.is_open = True
    return channel


@pytest.fixture
def mock_connection(mock_channel: MagicMock) -> MagicMock:
    connection: MagicMock = MagicMock(name='BlockingConnection')
    connection.is_open = True
    connection.channel.return_value = mock_channel
    return connection


@pytest.fixture
def patch_blocking_connection(mocker: MockerFixture, mock_connection: MagicMock) -> MagicMock:
    mocker.patch(
        target='django_rmq.connections.BlockingConnection',
        return_value=mock_connection,
    )
    return mock_connection
```

With the patch in place, `Producer.publish()` calls go to the mock channel,
so you can assert on what was published:

```python
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from django_rmq.producer import Producer


class TestMyProducer:
    def test_publish_sends_body(
        self,
        patch_blocking_connection: MagicMock,
        mock_channel: MagicMock,
    ) -> None:
        producer: Producer = Producer(queue='orders')
        producer.publish(body='{"order_id": 1}')

        mock_channel.basic_publish.assert_called_once()
        _, kwargs = mock_channel.basic_publish.call_args
        assert kwargs['routing_key'] == 'orders'
        assert kwargs['body'] == b'{"order_id": 1}'
        assert kwargs['mandatory'] is True
```

### Testing a consumer handler in isolation

A handler is just a callable. You can unit-test it directly by passing mock
objects for channel, method, and properties:

```python
from typing import Any
from unittest.mock import MagicMock

from myapp.consumers import handle_order


class TestHandleOrder:
    def test_acks_on_success(self) -> None:
        ch: MagicMock = MagicMock()
        method: MagicMock = MagicMock()
        method.delivery_tag = 42
        props: MagicMock = MagicMock()

        handle_order(ch=ch, method=method, props=props, body=b'{"order_id": 1}')

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
```

### Resetting django_rmq state between tests

`RabbitMQAppConfig.ready()` stores per-alias registries as module-level attributes
on `django_rmq`. Tests that register consumers or setup functions mutate global
state. The `reset_rmq_state` fixture in `tests/conftest.py` re-runs `ready()` in
teardown to restore a clean baseline automatically (it is `autouse=True`).

If your own test suite needs the same isolation, add a similar fixture to your
`conftest.py`:

```python
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def reset_rmq_state() -> Iterator[None]:
    yield
    from django.apps import apps as django_apps

    django_apps.get_app_config('django_rmq').ready()
```

---

## Contributing tests

See [Contribution Guide](/en/1.0.5/contrib.html) for the project conventions applied
when writing tests — typing, import style, and fixture patterns.
