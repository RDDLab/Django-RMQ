---
title: Clusters
sidebar_position: 11
---

A single connection alias can point at more than one broker node. Django-RMQ gives you **client-side failover**: pika
tries each configured node in order until one accepts the
connection. There is no proxying involved — on every connection attempt the library hands
pika a sequence of node addresses, and pika walks that sequence itself.

Two topologies are supported:

- A **client-side node list** — the alias enumerates every cluster node via `NODES`, and
  pika chooses which one to connect to.
- A **single endpoint** in front of the cluster — a load balancer or a DNS name with
  multiple A-records — where the alias still uses a plain `HOST`/`PORT` and the
  distribution/failover happens on the server side.

---

## Client-side node list (NODES)

Configure `NODES` with one entry per cluster node:

```python
# settings.py
RABBITMQ_CONNECTIONS: dict = {
    'default': {
        'NODES': [
            {'HOST': 'rmq-1.internal', 'PORT': 5672},
            {'HOST': 'rmq-2.internal', 'PORT': 5672},
            {'HOST': 'rmq-3.internal', 'PORT': 5672},
        ],
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

* `_resolve_nodes` in `django_rmq/apps.py` turns each `{'HOST': ..., 'PORT': ...}` entry into a
  `NodeConfig`;
* The remaining keys (`VIRTUAL_HOST`, `USER`, `PASSWORD`, `HEARTBEAT`,
  `BLOCKED_CONNECTION_TIMEOUT`, `SOCKET_TIMEOUT`, `STACK_TIMEOUT`) apply to every node in the list.

`RabbitMQConnectionManager.__init__` in `django_rmq/connections.py` then builds one
`pika.ConnectionParameters` per node (`_make_node_parameters`), all sharing the same
`PlainCredentials`, `virtual_host`, `heartbeat`, `blocked_connection_timeout`,
`socket_timeout`, and `stack_timeout`, and hands the whole sequence to `BlockingConnection`:

```python
# django_rmq/connections.py
setattr(self._local, attr, BlockingConnection(parameters=sequence))
```

pika's `BlockingConnection` accepts a sequence of `Parameters` objects and tries each one in
order until one connects successfully — this is exactly what gives you failover across the
cluster.

`NODES` is mutually exclusive with the scalar `HOST`/`PORT` form. See
[Configuration](./configuration.md) for the full parameter reference and the
validation error cases raised when both or neither are given.

---

## How failover works with reconnect

The node sequence is built freely on every connection attempt — not just the first one.
`RabbitMQConnectionManager._get_or_create_connection` calls
`_build_connection_sequence()` each time it needs to open a connection, so a reconnect gets
a fresh copy of the node list rather than reusing a stale one.

This ties directly into the existing [reconnect logic](./reliability.md): when a
producer hits a reconnectable error it calls `reset_producer_channel()` and reopens the
connection (retrying the publish once); a consumer reconnects with exponential backoff.
Because reopening the connection re-runs the node sequence from scratch, pika automatically
lands on whichever node is currently alive — no cluster-aware code is required in your
application.

A typical failover, step by step:

- Node A goes down.
- The active connection to A breaks.
- The reconnect path (producer retry or consumer backoff loop) reopens the connection.
- pika walks `[A, B, C]` again: A refuses the connection, B accepts.
- Publishing/consuming resumes transparently on B.

If A does not refuse the connection but silently drops packets (host down, network
partition), or accepts the TCP connection and never completes the AMQP handshake, pika
spends up to `SOCKET_TIMEOUT` / `STACK_TIMEOUT` on A before it moves on to B. See
Node timeouts and failover time.

`get_producer_connection` and `get_consumer_connection` log a debug entry every time a new
connection is opened, including the node list and the `shuffle` flag:

```python
# django_rmq/connections.py
logger.debug(
    {
        'source': source,
        'message': message,
        'data': {
            'nodes': [{'host': params.host, 'port': params.port} for params in sequence],
            'shuffle': self._shuffle_nodes,
        },
    }
)
```

Check this log line if you need to confirm which node a thread actually connected to.

---

## Spreading clients across the cluster (SHUFFLE_NODES)

`SHUFFLE_NODES` defaults to `False`: every client walks the `NODES` list in the order it was
declared, so every client prefers node 1 first. With many client processes this skews load
toward the first node in the list.

Set `SHUFFLE_NODES: True` to reshuffle the sequence on every connection attempt:

```python
# django_rmq/connections.py — RabbitMQConnectionManager._build_connection_sequence
sequence: list[ConnectionParameters] = list(self._node_parameters)
if self._shuffle_nodes:
    random.shuffle(sequence)
return sequence
```

`shuffle_nodes` comes from `RabbitMQConfig.shuffle_nodes`. Only the **copy** used for a given
connection attempt is shuffled — the configured `NODES` order in your settings is never
mutated, only the order tried on that particular connection changes.

Enable `SHUFFLE_NODES` for clusters serving many client processes, so connections spread
across nodes instead of piling onto the first one.

---

## Node timeouts and failover time

pika walks the node sequence **sequentially**: it does not try the next node until the
current one has failed. How long a bad node holds up the connection depends on how it
fails:

| What the node does                                                     | Cost per attempt                          |
|------------------------------------------------------------------------|-------------------------------------------|
| Refuses the connection (port closed, process down, host reachable)     | Fast: fails immediately                   |
| Drops packets silently (host down, firewall `DROP`, network partition) | Up to `SOCKET_TIMEOUT` (default `10.0` s) |
| Accepts TCP but the AMQP handshake hangs                               | Up to `STACK_TIMEOUT` (default `15.0` s)  |

The worst-case delay before pika reaches a live node is the **sum** over all bad nodes
tried before it. With three nodes and the defaults (values for illustration):

- the first two nodes drop packets — about 20 s (2 × 10 s) before the third one is tried;
- the first two nodes hang on the handshake — about 30 s (2 × 15 s).

This price is paid on every connect and reconnect:

- the first producer connection in a thread;
- the reconnect after `reset_producer_channel()` — the `publish` call blocks for that time;
- every consumer reconnect (on top of the backoff delay).

See [Reliability](./reliability.md) for the reconnect logic.

### Recommendation

Lower `SOCKET_TIMEOUT` and `STACK_TIMEOUT` on a cluster alias, and keep
`STACK_TIMEOUT >= SOCKET_TIMEOUT`:

```python
# settings.py
RABBITMQ_CONNECTIONS: dict = {
    'default': {
        'NODES': [
            {'HOST': 'rmq-1.internal', 'PORT': 5672},
            {'HOST': 'rmq-2.internal', 'PORT': 5672},
            {'HOST': 'rmq-3.internal', 'PORT': 5672},
        ],
        # ... the remaining keys as above ...
        'SOCKET_TIMEOUT': 3.0,  # example values — tune for your network/TLS
        'STACK_TIMEOUT': 6.0,
    },
}
```

Don't set them too low: on a slow network or with TLS a healthy node may fail to answer
in time and the client will skip it. See
Connection timeouts for details.

### Healthcheck

The `check_rabbitmq_connections` command does **not** walk the nodes sequentially. It probes
all nodes in parallel with its own timeouts from `RABBITMQ_HEALTHCHECK`, and ignores the
alias `SOCKET_TIMEOUT` / `STACK_TIMEOUT` and `SHUFFLE_NODES`. An alias is reported as OK as
soon as the first node answers, so a dead node does not delay the verdict. See
[`check_rabbitmq_connections`](./management-commands.md#check_rabbitmq_connections) and
`RABBITMQ_HEALTHCHECK`.

---

## Alternative: load balancer or DNS

Instead of listing every node via `NODES`, you can put the cluster behind a single address:
a TCP load balancer (e.g. HAProxy) or a DNS name with multiple A-records pointing at the
cluster nodes. In that case a plain `HOST`/`PORT` is enough — pika resolves and connects to
whichever address responds, and distribution/failover happens on the server side.

Trade-offs:

- **`NODES` (client-side)** — no extra infrastructure to run; the client knows about every
  node; failover logic lives in the application (via pika).
- **Load balancer / DNS (server-side)** — a single endpoint to configure; health checks are
  centralized on the LB/DNS side; requires running and maintaining that infrastructure; the
  client configuration stays simple.

The two approaches are not mutually exclusive at the protocol level, but a given alias
typically picks one or the other.

---

## Quorum queues

Quorum queues are orthogonal to cluster addressing — django_rmq declares them the same way
as any other queue type, via the `queue_type` field on `QueueConfig`
(see [`QueueType`](./api-reference.md#queuetype) in the API reference):

```python
from django_rmq.queues.queue_config import QueueConfig,
    QueueType

orders_queue: QueueConfig = QueueConfig(name='orders', queue_type=QueueType.QUORUM)
```

Declaring the queue with this config sets `x-queue-type: quorum` on `queue_declare`. Define
`orders_queue` once (e.g. in `myapp/queues.py`) and share it between the producer, the
consumer, and any setup function that references the queue — see [Topology](./topology.md).

Or declare it from a raw setup function instead, registered through the setup registry
(see [Registries](./registries.md)) — a lower-level alternative useful when the queue
needs arguments beyond what `QueueConfig` exposes:

```python
from pika.adapters.blocking_connection import BlockingChannel


def setup_quorum(channel: BlockingChannel) -> None:
    channel.queue_declare(
        queue='orders',
        durable=True,
        arguments={'x-queue-type': 'quorum'},
    )
```

Register it the same way as any other setup function:

```python
from django_rmq.registries.setup_registry import get_setup_registry

get_setup_registry().register(fn=setup_quorum)
```

Publisher confirms are already enabled on every producer channel (`confirm_delivery()` in
`django_rmq/connections.py` — see [Reliability](./reliability.md)), which pairs well
with quorum queues for durability across the cluster.

---

## See also

- [Configuration](./configuration.md) — the full `NODES`/`SHUFFLE_NODES`/`SOCKET_TIMEOUT`/
  `STACK_TIMEOUT` parameter reference and validation error cases.
- [Management Commands](./management-commands.md) — `check_rabbitmq_connections` probes
  every node in parallel.
- [Reliability](./reliability.md) — producer retry-once and consumer reconnect with
  backoff.
- [Multiple Connections](./multiple-connections.md) — running several aliases in one
  project.
- [Topology](./topology.md) — declaring exchanges, queues, and bindings via setup
  functions.
- [Testing](./testing.md) — cluster integration tests that exercise this failover
  behavior against a real three-node RabbitMQ cluster.
