---
title: Configuration
sidebar_position: 3
---

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
on `django_rmq` and are available from that point on. `ready()` also parses the optional `RABBITMQ_HEALTHCHECK` setting
into `django_rmq.healthcheck_config` — see `RABBITMQ_HEALTHCHECK`.

If `RABBITMQ_CONNECTIONS` is missing or empty when `ready()` runs, Django raises `ImproperlyConfigured` and refuses to
start.

## `RABBITMQ_CONNECTIONS`

`RABBITMQ_CONNECTIONS` is a `dict` that maps an alias name to a connection parameters dict. Node addressing is given
either as a scalar `HOST`/`PORT` pair (a single broker) or as a `NODES` list (a cluster); the remaining keys are
shared by every alias regardless of which form is used.

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

| Key                          | Type         | `RabbitMQConfig` field               | Description                                                                                                                                                                                                                                                                       |
|------------------------------|--------------|--------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `HOST`                       | `str`        | `nodes` (single `NodeConfig.host`)   | Broker hostname or IP for a single-node alias. Mutually exclusive with `NODES`.                                                                                                                                                                                                   |
| `PORT`                       | `int`        | `nodes` (single `NodeConfig.port`)   | Broker AMQP port (typically `5672`) for a single-node alias. Mutually exclusive with `NODES`.                                                                                                                                                                                     |
| `NODES`                      | `list[dict]` | `nodes` (one `NodeConfig` per entry) | Cluster node list; each item is `{'HOST': str, 'PORT': int}`. Mutually exclusive with `HOST`/`PORT`. See [Clusters](./clusters.md).                                                                                                                                               |
| `SHUFFLE_NODES`              | `bool`       | `shuffle_nodes`                      | Optional; default `False`. Reshuffles node order on every connection attempt to spread clients across the cluster. Only meaningful with `NODES`.                                                                                                                                  |
| `VIRTUAL_HOST`               | `str`        | `virtual_host`                       | AMQP virtual host; shared by all nodes of the alias.                                                                                                                                                                                                                              |
| `USER`                       | `str`        | `user`                               | Username for PlainCredentials; shared by all nodes.                                                                                                                                                                                                                               |
| `PASSWORD`                   | `str`        | `password`                           | Password for PlainCredentials; shared by all nodes.                                                                                                                                                                                                                               |
| `HEARTBEAT`                  | `int`        | `heartbeat`                          | Heartbeat interval in seconds; shared by all nodes.                                                                                                                                                                                                                               |
| `BLOCKED_CONNECTION_TIMEOUT` | `int`        | `blocked_connection_timeout`         | Seconds to wait while the broker blocks the connection; shared by all nodes.                                                                                                                                                                                                      |
| `RECONNECT_INITIAL_BACKOFF`  | `float`      | `reconnect_initial_backoff`          | Initial consumer reconnect delay in seconds.                                                                                                                                                                                                                                      |
| `RECONNECT_MAX_BACKOFF`      | `float`      | `reconnect_max_backoff`              | Maximum consumer reconnect delay (cap for exponential backoff).                                                                                                                                                                                                                   |
| `SOCKET_TIMEOUT`             | `float`      | `socket_timeout`                     | Optional; default `10.0` (pika's default). Seconds to wait for the TCP connection to one node; `int` accepted. Shared by all nodes. Each unreachable node tried before a live one can add up to this much to every (re)connect — see Connection timeouts. |
| `STACK_TIMEOUT`              | `float`      | `stack_timeout`                      | Optional; default `15.0` (pika's default). Seconds to wait for the full TCP + AMQP bring-up of one node. Shared by all nodes.                                                                                                                                                     |

`HOST`/`PORT` and `NODES` both resolve to the same `nodes` tuple on `RabbitMQConfig` — the scalar form is just
syntactic sugar for a single-element `nodes` tuple.

`RabbitMQConfig` is a frozen dataclass. After `ready()` completes each alias has its own immutable config instance;
modifying the settings dict at runtime has no effect.

### Cluster nodes (NODES)

To point one alias at several broker nodes, use `NODES` instead of `HOST`/`PORT`. `VIRTUAL_HOST`, `USER`,
`PASSWORD`, and the timeout/backoff keys (including `SOCKET_TIMEOUT` and `STACK_TIMEOUT`) still apply to every node in
the list. `NODES` and `HOST`/`PORT` are
mutually exclusive — configure one or the other, never both. See [Clusters](./clusters.md) for failover
behavior and `SHUFFLE_NODES`.

```python
RABBITMQ_CONNECTIONS: dict[str, dict[str, object]] = {
    'default': {
        'NODES': [
            {'HOST': 'rmq-1.internal', 'PORT': 5672},
            {'HOST': 'rmq-2.internal', 'PORT': 5672},
            {'HOST': 'rmq-3.internal', 'PORT': 5672},
        ],
        'SHUFFLE_NODES': True,
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

### Connection timeouts (SOCKET_TIMEOUT, STACK_TIMEOUT)

Two optional per-alias keys control how long pika waits while connecting to a single node:

- `SOCKET_TIMEOUT` — seconds to wait for the TCP connection to one node. Default `10.0`.
- `STACK_TIMEOUT` — seconds to wait for the full TCP + AMQP bring-up of one node. Default `15.0`.

The defaults are pika's own, so nothing changes unless you set these keys. Both values are stored on `RabbitMQConfig`
(`socket_timeout`, `stack_timeout`) and passed to `pika.ConnectionParameters` for every node by
`RabbitMQConnectionManager._make_node_parameters` (`django_rmq/connections.py`).

pika tries the nodes one after another. A node that actively refuses the connection is skipped almost instantly, but a
node that silently drops packets (host down, firewall `DROP`, network partition) costs up to `SOCKET_TIMEOUT`, and a
node
that accepts TCP but never completes the AMQP handshake costs up to `STACK_TIMEOUT`. These delays add up for every bad
node tried before a live one, on every connect and reconnect. See Clusters for details.

Both values must be a positive `int` or `float` (converted to `float`). `bool` values and strings are rejected with
`ImproperlyConfigured` at startup.

```python
RABBITMQ_CONNECTIONS: dict[str, dict[str, object]] = {
    'default': {
        'NODES': [
            {'HOST': 'rmq-1.internal', 'PORT': 5672},
            {'HOST': 'rmq-2.internal', 'PORT': 5672},
            {'HOST': 'rmq-3.internal', 'PORT': 5672},
        ],
        'SHUFFLE_NODES': True,
        'SOCKET_TIMEOUT': 3.0,  # example values — tune for your network/TLS
        'STACK_TIMEOUT': 6.0,
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

Setting the timeouts too low causes spurious connection failures on slow networks or with TLS, so choose values that
comfortably cover a normal connect in your environment.

These keys are not used by `check_rabbitmq_connections`; the healthcheck has its own timeouts — see
`RABBITMQ_HEALTHCHECK`.

## `RABBITMQ_HEALTHCHECK`

`RABBITMQ_HEALTHCHECK` is an optional global setting (not per alias) used only by the `check_rabbitmq_connections`
management command. It is a `dict` with three optional keys; an empty `{}` means all defaults.

| Key              | Type    | Default | `HealthcheckConfig` field | Description                                                                                                                                                                         |
|------------------|---------|---------|---------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `DEADLINE`       | `float` | `15.0`  | `deadline`                | Overall budget in seconds for the whole check (all aliases). When it expires, aliases that are still undecided fail with `TimeoutError`. `--timeout` overrides it for a single run. |
| `SOCKET_TIMEOUT` | `float` | `5.0`   | `socket_timeout`          | Seconds to wait for the TCP connection to one node during the probe.                                                                                                                |
| `STACK_TIMEOUT`  | `float` | `10.0`  | `stack_timeout`           | Seconds to wait for the full TCP + AMQP bring-up of one node during the probe.                                                                                                      |

The probe ignores the per-alias `SOCKET_TIMEOUT`/`STACK_TIMEOUT` and `SHUFFLE_NODES`, so its duration does not depend on
node order.

```python
RABBITMQ_HEALTHCHECK: dict[str, float] = {
    'DEADLINE': 15.0,
    'SOCKET_TIMEOUT': 5.0,
    'STACK_TIMEOUT': 10.0,
}
```

These are the defaults; omit the setting to use them.

Validation happens in `RabbitMQAppConfig.ready()`, which runs in every Django process. An invalid setting therefore
fails when the worker starts, even though the healthcheck command itself skips system checks (a probe started with an
invalid setting fails with a traceback). The following raise `ImproperlyConfigured`:

- the setting is not a `dict`;
- it contains an unknown key (allowed: `DEADLINE`, `SOCKET_TIMEOUT`, `STACK_TIMEOUT`);
- a value is not a positive number of seconds (`bool` and strings are rejected).

There is no cross-check between the keys. Keep the per-node timeouts at or below `DEADLINE`; otherwise a hanging node is
reported as `no answer` instead of with its own error. For how these values fit into a container probe timeout, see
Healthcheck timing budget.

The parsed value is available as `django_rmq.healthcheck_config` (a `HealthcheckConfig`, or `None` before `ready()`
runs); see `HealthcheckConfig`.

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

See [Multiple Connections](./multiple-connections.md) for a complete multi-alias example.

## Error cases

| Situation                                                                                   | Exception              | Message                                                                                                                     |
|---------------------------------------------------------------------------------------------|------------------------|-----------------------------------------------------------------------------------------------------------------------------|
| `RABBITMQ_CONNECTIONS` missing or empty                                                     | `ImproperlyConfigured` | `django_rmq requires RABBITMQ_CONNECTIONS …`                                                                                |
| `'django_rmq'` not in `INSTALLED_APPS`                                                      | `ImproperlyConfigured` | `django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.`                                                        |
| `using` omitted with multiple aliases                                                       | `ImproperlyConfigured` | `Multiple RabbitMQ connections configured (…); pass using='<alias>' explicitly.`                                            |
| `using` set to an unknown alias                                                             | `ImproperlyConfigured` | `Unknown RabbitMQ alias '<alias>'.`                                                                                         |
| Both `NODES` and `HOST`/`PORT` given for one alias                                          | `ImproperlyConfigured` | `RabbitMQ alias '<alias>': use either 'NODES' or 'HOST'/'PORT', not both.`                                                  |
| Neither `NODES` nor `HOST`/`PORT` given                                                     | `ImproperlyConfigured` | `RabbitMQ alias '<alias>': define node addressing via 'NODES' or 'HOST'/'PORT'.`                                            |
| `NODES` present but empty list                                                              | `ImproperlyConfigured` | `RabbitMQ alias '<alias>': 'NODES' must be a non-empty list.`                                                               |
| A `NODES` entry missing `HOST` or `PORT`                                                    | `ImproperlyConfigured` | `RabbitMQ alias '<alias>': NODES[<index>] must define both 'HOST' and 'PORT'.`                                              |
| `SOCKET_TIMEOUT` / `STACK_TIMEOUT` is not a positive number (`0`, negative, `bool`, string) | `ImproperlyConfigured` | `RabbitMQ alias '<alias>': 'SOCKET_TIMEOUT' must be a positive number of seconds, got <repr>.` (same for `'STACK_TIMEOUT'`) |
| `RABBITMQ_HEALTHCHECK` is not a `dict`                                                      | `ImproperlyConfigured` | `` `RABBITMQ_HEALTHCHECK` must be a dict. ``                                                                                |
| `RABBITMQ_HEALTHCHECK` has an unknown key                                                   | `ImproperlyConfigured` | `` `RABBITMQ_HEALTHCHECK`: unknown key(s) <KEYS>; allowed: DEADLINE, SOCKET_TIMEOUT, STACK_TIMEOUT. ``                      |
| `RABBITMQ_HEALTHCHECK` value is not a positive number                                       | `ImproperlyConfigured` | `` `RABBITMQ_HEALTHCHECK`: 'DEADLINE' must be a positive number of seconds, got <repr>. `` (same for the other keys)        |

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
        'SOCKET_TIMEOUT': float(os.environ.get('RMQ_SOCKET_TIMEOUT', '10.0')),
        'STACK_TIMEOUT': float(os.environ.get('RMQ_STACK_TIMEOUT', '15.0')),
    },
}
```

You can also use `django-environ`, `python-decouple`, or any other env-loading library — `RABBITMQ_CONNECTIONS` is a
plain Python dict, so any value source works.
