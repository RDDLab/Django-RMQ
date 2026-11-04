---
title: API Reference
sidebar_position: 13
---

Flat reference for every public symbol in `django_rmq`. Signatures and parameter
descriptions are taken directly from the source code.

---

## Producer

```python
from django_rmq.producer import Producer
```

Publishes messages to RabbitMQ through a thread-local blocking channel.

### `Producer.__init__`

```python
def __init__(
    self,
    exchange: str = '',
    queue: QueueConfig | str = '',
    using: str | None = None,
) -> None
```

| Parameter  | Type                 | Default | Description                                                                                                                                               |
|------------|----------------------|---------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `exchange` | `str`                | `''`    | Exchange name. Empty string means the default (direct) exchange.                                                                                          |
| `queue`    | `QueueConfig \| str` | `''`    | Queue configuration or name. Used as default routing key; declared lazily on first publish. Empty string disables queue declaration (exchange-only mode). |
| `using`    | `str \| None`        | `None`  | Connection alias from `RABBITMQ_CONNECTIONS`. May be omitted when exactly one alias is configured.                                                        |

### `Producer.publish`

```python
def publish(
    self,
    body: str | bytes,
    routing_key: str | None = None,
    properties: BasicProperties | None = None,
) -> None
```

| Parameter     | Type                      | Default  | Description                                                                                                                                  |
|---------------|---------------------------|----------|----------------------------------------------------------------------------------------------------------------------------------------------|
| `body`        | `str \| bytes`            | required | Message body. Strings are encoded to bytes (UTF-8).                                                                                          |
| `routing_key` | `str \| None`             | `None`   | Routing key. Defaults to `self.queue` (the queue name) when not provided.                                                                    |
| `properties`  | `BasicProperties \| None` | `None`   | AMQP message properties. When omitted, created with `content_type='application/json'`. `delivery_mode` is always forced to `2` (persistent). |

**Returns:** `None`

**Raises:**

- `pika.exceptions.UnroutableError` — broker returned the message because no queue matched the routing key (requires
  publisher confirms + `mandatory=True`, both always enabled).
- `pika.exceptions.NackError` — broker nacked the message.
- Any exception from `_RECONNECTABLE_ERRORS` if both the first attempt and the single retry fail.

### `Producer.__call__`

Allows a `Producer` instance to be used as a function decorator. The decorated
function must return `str`, `bytes`, or `None`. The return value is published
automatically; `None` skips publishing.

```python
def __call__(
    self,
    func: Callable[..., str | bytes | None],
) -> Callable[..., str | bytes | None]
```

**Raises:** `TypeError` if the decorated function returns a type other than `str`,
`bytes`, or `None`.

**Example:**

```python
from django_rmq.producer import Producer

producer: Producer = Producer(queue='notifications')


@producer
def build_notification(user_id: int) -> str:
    return f'{{"user_id": {user_id}}}'
```

---

## Consumer

```python
from django_rmq.consumer import Consumer
```

Consumes messages from a single RabbitMQ queue with one registered handler.
Reconnects on transient AMQP errors with exponential backoff.

### `Consumer.__init__`

```python
def __init__(
    self,
    queue: QueueConfig | str,
    prefetch_count: int = 1,
    reconnect_initial_backoff: float | None = None,
    reconnect_max_backoff: float | None = None,
    using: str | None = None,
) -> None
```

| Parameter                   | Type                 | Default  | Description                                                                                                                |
|-----------------------------|----------------------|----------|----------------------------------------------------------------------------------------------------------------------------|
| `queue`                     | `QueueConfig \| str` | required | Queue to consume from. `QueueConfig` triggers an active declare with arguments; a plain string triggers a durable declare. |
| `prefetch_count`            | `int`                | `1`      | Maximum unacknowledged messages delivered at once (`basic_qos`).                                                           |
| `reconnect_initial_backoff` | `float \| None`      | `None`   | Initial reconnect delay in seconds. Falls back to the alias config value when `None`.                                      |
| `reconnect_max_backoff`     | `float \| None`      | `None`   | Maximum reconnect delay in seconds (exponential backoff cap). Falls back to alias config when `None`.                      |
| `using`                     | `str \| None`        | `None`   | Connection alias. May be omitted when exactly one alias is configured.                                                     |

### `Consumer.handler`

```python
def handler(self, func: MessageCallback) -> MessageCallback
```

Registers a callback for incoming messages. Can be used as a decorator.

**Raises:** `RuntimeError` if a handler is already registered on this consumer.

### `Consumer.__call__`

Shorthand for `@consumer.handler`. Identical behavior.

```python
def __call__(self, func: MessageCallback) -> MessageCallback
```

### `Consumer.consume`

```python
def consume(self, stop_event: threading.Event | None = None) -> None
```

Starts the consume loop. Reconnects on transient errors. Exits when `stop_event`
is set or an unrecoverable error is raised.

| Parameter    | Type                      | Default | Description                                                                                                                     |
|--------------|---------------------------|---------|---------------------------------------------------------------------------------------------------------------------------------|
| `stop_event` | `threading.Event \| None` | `None`  | Event that signals graceful shutdown. When `None`, an internal event (never set) is created — the consumer runs until an error. |

### `Consumer` properties

| Property         | Type          | Description                                                           |
|------------------|---------------|-----------------------------------------------------------------------|
| `prefetch_count` | `int`         | Maximum unacknowledged messages delivered at once.                    |
| `using`          | `str \| None` | Connection alias, or `None` when the single alias is used implicitly. |
| `handler_name`   | `str`         | Name of the registered handler function, or `'unregistered'` if none. |

---

## MessageCallback

```python
from django_rmq.consumer import MessageCallback
```

Type alias for the handler callable signature:

```python
MessageCallback = Callable[
    [BlockingChannel, Basic.Deliver, BasicProperties, bytes],
    None,
]
```

| Argument | Type              | Description                                                                    |
|----------|-------------------|--------------------------------------------------------------------------------|
| `ch`     | `BlockingChannel` | Channel the message was delivered on. Used to call `basic_ack` / `basic_nack`. |
| `method` | `Basic.Deliver`   | Delivery metadata, including `delivery_tag`.                                   |
| `props`  | `BasicProperties` | AMQP message properties.                                                       |
| `body`   | `bytes`           | Raw message body.                                                              |

---

## QueueConfig

```python
from django_rmq.queues.queue_config import QueueConfig,

QueueType
```

Frozen dataclass for declarative queue configuration.

```python
@dataclass(frozen=True)
class QueueConfig:
    name: str
    durable: bool = True
    queue_type: QueueType | None = None
    dead_letter_exchange: str | None = None
    dead_letter_routing_key: str | None = None
```

| Field                     | Type                | Default  | Description                                                                        |
|---------------------------|---------------------|----------|------------------------------------------------------------------------------------|
| `name`                    | `str`               | required | Queue name. Also used as `str(queue_config)`.                                      |
| `durable`                 | `bool`              | `True`   | Queue survives broker restarts.                                                    |
| `queue_type`              | `QueueType \| None` | `None`   | Sets `x-queue-type` on declaration. `None` uses the broker's `default_queue_type`. |
| `dead_letter_exchange`    | `str \| None`       | `None`   | Exchange dead-lettered messages are routed to (`x-dead-letter-exchange`).          |
| `dead_letter_routing_key` | `str \| None`       | `None`   | Routing key for dead-lettered messages (`x-dead-letter-routing-key`).              |

### `QueueType`

Enum of the RabbitMQ queue types django_rmq knows how to declare; its value is serialized to the broker as the
`x-queue-type` argument.

| Member    | Value       |
|-----------|-------------|
| `CLASSIC` | `'classic'` |
| `QUORUM`  | `'quorum'`  |
| `STREAM`  | `'stream'`  |

`QueueType` subclasses `str` (instead of the 3.11+ `StrEnum`, unavailable on Python 3.10), so each member is an actual
string and serializes to the broker as-is. When `queue_type` is left unset on a `QueueConfig`, the broker applies its
own `default_queue_type`.

### `QueueConfig.arguments` property

```python
@property
def arguments(self) -> dict[str, Any] | None
```

Builds the AMQP `arguments` dict for queue declaration from `queue_type`
(`x-queue-type`) and the dead-letter fields. Returns `None` when none of them
are set.

---

## RabbitMQConfig

```python
from django_rmq.dto.rabbitmq_config import RabbitMQConfig
```

Frozen dataclass holding the resolved configuration for one connection alias.
Created internally by `RabbitMQAppConfig.ready()` from the `RABBITMQ_CONNECTIONS`
setting. Exposed on `RabbitMQConnectionManager.config`.

```python
@dataclass(frozen=True)
class RabbitMQConfig:
    nodes: tuple[NodeConfig, ...]
    virtual_host: str
    user: str
    password: str
    heartbeat: int
    blocked_connection_timeout: int
    reconnect_initial_backoff: float
    reconnect_max_backoff: float
    shuffle_nodes: bool = False
    socket_timeout: float = 10.0
    stack_timeout: float = 15.0
```

An alias may point at one node (a plain broker) or several (a cluster). All nodes share
the same virtual host and credentials.

| Field                        | Type                     | Default  | Description                                                                                                   |
|------------------------------|--------------------------|----------|---------------------------------------------------------------------------------------------------------------|
| `nodes`                      | `tuple[NodeConfig, ...]` | required | One or more node addresses. pika tries them in order until one accepts the connection (client-side failover). |
| `virtual_host`               | `str`                    | required | AMQP virtual host to connect to.                                                                              |
| `user`                       | `str`                    | required | Username for `PlainCredentials`.                                                                              |
| `password`                   | `str`                    | required | Password for `PlainCredentials`.                                                                              |
| `heartbeat`                  | `int`                    | required | Heartbeat interval in seconds negotiated with the broker.                                                     |
| `blocked_connection_timeout` | `int`                    | required | Seconds to wait while the broker blocks the connection before failing.                                        |
| `reconnect_initial_backoff`  | `float`                  | required | Initial consumer reconnect delay in seconds.                                                                  |
| `reconnect_max_backoff`      | `float`                  | required | Maximum consumer reconnect delay in seconds (cap for the exponential backoff).                                |
| `shuffle_nodes`              | `bool`                   | `False`  | Reshuffle the node order on every connection attempt so clients spread across the cluster.                    |
| `socket_timeout`             | `float`                  | `10.0`   | Seconds to wait for the TCP connection to a single node (pika `socket_timeout`).                              |
| `stack_timeout`              | `float`                  | `15.0`   | Seconds to wait for the full TCP + AMQP bring-up of a single node (pika `stack_timeout`).                     |

### `NodeConfig`

```python
from django_rmq.dto.rabbitmq_config import NodeConfig
```

```python
@dataclass(frozen=True)
class NodeConfig:
    host: str
    port: int
```

Immutable address of a single RabbitMQ node within a connection alias.

| Field  | Type  | Description                  |
|--------|-------|------------------------------|
| `host` | `str` | Node hostname or IP address. |
| `port` | `int` | Node AMQP port.              |

---

## HealthcheckConfig

```python
from django_rmq.dto.healthcheck_config import HealthcheckConfig
```

```python
@dataclass(frozen=True)
class HealthcheckConfig:
    deadline: float = 15.0
    socket_timeout: float = 5.0
    stack_timeout: float = 10.0
```

| Field            | Type    | Default | Setting key      | Description                                                                                                              |
|------------------|---------|---------|------------------|--------------------------------------------------------------------------------------------------------------------------|
| `deadline`       | `float` | `15.0`  | `DEADLINE`       | Overall budget in seconds for checking every alias. When it expires, aliases without a live node are reported as failed. |
| `socket_timeout` | `float` | `5.0`   | `SOCKET_TIMEOUT` | Seconds to wait for the TCP connection to a single node.                                                                 |
| `stack_timeout`  | `float` | `10.0`  | `STACK_TIMEOUT`  | Seconds to wait for the full TCP + AMQP bring-up of a single node.                                                       |

---

## RabbitMQConnectionManager

```python
from django_rmq.connections import RabbitMQConnectionManager
```

Manages thread-local connections for producer and consumer roles. Instantiated
once per alias by `RabbitMQAppConfig.ready()`.

### `RabbitMQConnectionManager.__init__`

```python
def __init__(self, config: RabbitMQConfig) -> None:
```

Builds one `ConnectionParameters` per node, each with the alias `socket_timeout` and
`stack_timeout`.

### `RabbitMQConnectionManager.get_producer_connection`

```python
def get_producer_connection(self) -> BlockingConnection
```

Returns the thread-local `BlockingConnection` used by producers on the current
thread. Creates it on first call; reuses the cached instance while it is open.

### `RabbitMQConnectionManager.get_consumer_connection`

```python
def get_consumer_connection(self) -> BlockingConnection
```

Returns the thread-local `BlockingConnection` used by consumers on the current
thread. Kept separate from the producer connection to allow safe publishing from
inside a handler.

### `RabbitMQConnectionManager.get_producer_channel`

```python
def get_producer_channel(self) -> BlockingChannel
```

Returns the thread-local producer channel with publisher confirms enabled (`confirm_delivery()`). Creates it on first
call; reuses while open.

### `RabbitMQConnectionManager.reset_producer_channel`

```python
def reset_producer_channel(self) -> None
```

Closes and discards the cached producer channel and connection. Called
automatically by `Producer.publish` after a reconnectable error so the next
publish opens a fresh channel. Safe to call even when no channel is cached.

### `RabbitMQConnectionManager.build_probe_parameters`

```python
def build_probe_parameters(
    self,
    socket_timeout: float,
    stack_timeout: float,
) -> list[ConnectionParameters]
```

| Parameter        | Type    | Default  | Description                                                 |
|------------------|---------|----------|-------------------------------------------------------------|
| `socket_timeout` | `float` | required | Seconds to wait for the TCP connection to a node.           |
| `stack_timeout`  | `float` | required | Seconds to wait for the full TCP + AMQP bring-up of a node. |

**Returns:** `list[ConnectionParameters]` — one entry per node, in `NODES` order.

Builds independent per-node connection parameters for probing nodes one by one. The
order follows `NODES` and is never shuffled; a new list is built on every call and
nothing is cached. No connection is opened. Credentials, virtual host, heartbeat, and
blocked-connection timeout are the same as for the alias; the alias `socket_timeout` /
`stack_timeout` and `shuffle_nodes` are ignored. Used by `check_rabbitmq_connections`.

---

## get_connection_manager

```python
from django_rmq.connections import get_connection_manager
```

```python
def get_connection_manager(using: str | None = None) -> RabbitMQConnectionManager
```

Returns the `RabbitMQConnectionManager` for the given alias.

| Parameter | Type          | Default | Description                                                            |
|-----------|---------------|---------|------------------------------------------------------------------------|
| `using`   | `str \| None` | `None`  | Alias to resolve. May be omitted when exactly one alias is configured. |

**Raises:** `ImproperlyConfigured` — alias not found, ambiguous (multiple aliases,
`using` omitted), or `django_rmq` not initialized.

---

## ConsumersRegistry

```python
from django_rmq.registries.registry import ConsumersRegistry
```

Holds the consumers registered for one connection alias.

### `ConsumersRegistry.register`

```python
def register(self, consumer: Consumer) -> None
```

Adds a consumer to the registry.

### `ConsumersRegistry.all`

```python
def all(self) -> list[Consumer]
```

Returns a copy of all registered consumers. Mutating the returned list does not
affect the registry.

---

## get_consumers_registry

```python
from django_rmq.registries.registry import get_consumers_registry
```

```python
def get_consumers_registry(using: str | None = None) -> ConsumersRegistry
```

Returns the `ConsumersRegistry` for the given alias.

**Raises:** `ImproperlyConfigured` — same conditions as `get_connection_manager`.

---

## SetupRegistry

```python
from django_rmq.registries.setup_registry import SetupRegistry
```

Holds idempotent topology-setup functions for one connection alias.

### `SetupRegistry.register`

```python
def register(self, fn: SetupFn) -> None
```

Adds a setup function to the registry. Functions are invoked in registration order.

### `SetupRegistry.run_all`

```python
def run_all(self, channel: BlockingChannel) -> None
```

Runs every registered setup function on the given channel in registration order.

---

## get_setup_registry

```python
from django_rmq.registries.setup_registry import get_setup_registry
```

```python
def get_setup_registry(using: str | None = None) -> SetupRegistry
```

Returns the `SetupRegistry` for the given alias.

**Raises:** `ImproperlyConfigured` — same conditions as `get_connection_manager`.

---

## SetupFn

```python
from django_rmq.registries.setup_registry import SetupFn
```

Type alias for a topology setup callable:

```python
SetupFn = Callable[[BlockingChannel], None]
```

A `SetupFn` receives an open `BlockingChannel` and must be idempotent (safe to
call multiple times with the same outcome).

---

## RabbitMQAppConfig

```python
from django_rmq.apps import RabbitMQAppConfig
```

Django `AppConfig` for `django_rmq`. Registered automatically when `'django_rmq'`
is in `INSTALLED_APPS`.

### `RabbitMQAppConfig.ready`

```python
def ready(self) -> None
```

Reads `RABBITMQ_CONNECTIONS` from Django settings and builds, per alias, one
`RabbitMQConnectionManager`, one `SetupRegistry`, and one `ConsumersRegistry`.
Stores them on the `django_rmq` module as `connection_managers`,
`setup_registries`, and `consumers_registries`. Also parses the optional
`RABBITMQ_HEALTHCHECK` setting into `django_rmq.healthcheck_config`, so its errors
surface when the worker starts rather than in the healthcheck probe.

**Raises:** `ImproperlyConfigured` — `RABBITMQ_CONNECTIONS` is missing or empty, node
addressing is missing or invalid, `SOCKET_TIMEOUT` / `STACK_TIMEOUT` is not a positive
number, or `RABBITMQ_HEALTHCHECK` is invalid. See the
[Error cases](./configuration.md) in the Configuration guide.

---

## Module globals (`django_rmq`)

```python
import django_rmq

django_rmq.connection_managers  # dict[str, RabbitMQConnectionManager] | None
django_rmq.setup_registries  # dict[str, SetupRegistry] | None
django_rmq.consumers_registries  # dict[str, ConsumersRegistry] | None
django_rmq.healthcheck_config  # HealthcheckConfig | None
```

All four are `None` until `RabbitMQAppConfig.ready()` runs. Use the accessor
functions (`get_connection_manager`, `get_consumers_registry`, `get_setup_registry`)
rather than accessing the first three dicts directly. There is no accessor for
`healthcheck_config`; read it from the module (`check_rabbitmq_connections` falls back to
`HealthcheckConfig()` when it is `None`).

---

## Management commands

### `setup_rabbitmq_topology`

```bash
uv run python manage.py setup_rabbitmq_topology [--using ALIAS]
```

Declares all exchanges, queues, and bindings registered in `SetupRegistry` for
one or all aliases. Idempotent — safe to run on every deploy.

| Option          | Description                                                |
|-----------------|------------------------------------------------------------|
| `--using ALIAS` | Run only for the named alias. Omit to run for every alias. |

After setup it prints a report of declared exchanges, queues, and bindings,
de-duplicated by name.

### `check_rabbitmq_connections`

```bash
uv run python manage.py check_rabbitmq_connections [--using ALIAS] [--format {json,text}] [--timeout SECONDS] [--skip-checks]
```

Healthcheck for container probes. Probes every node of one or all aliases in parallel (opens a connection and closes it
immediately) with the timeouts from `RABBITMQ_HEALTHCHECK`. An alias is healthy as soon as one of its nodes answers;
aliases without a live node fail when all nodes fail or the deadline expires. Exits with code `0` when every alias is
healthy and `1` otherwise.

| Option                 | Description                                                                                                     |
|------------------------|-----------------------------------------------------------------------------------------------------------------|
| `--using ALIAS`        | Check only the named alias. Omit to check every alias.                                                          |
| `--format {json,text}` | Output format: `text` (default, logfmt-style `key=value`) or `json` (one object per line).                      |
| `--timeout SECONDS`    | Overall deadline in seconds. Must be greater than `0`. Defaults to `RABBITMQ_HEALTHCHECK['DEADLINE']` (`15.0`). |
| `--skip-checks`        | No-op, kept for backward compatibility: the command never runs system checks.                                   |

See [Management Commands](./management-commands.md) for output events, exit codes, and examples.

### `start_consumers`

```bash
uv run python manage.py start_consumers [--using ALIAS]
```

Starts every consumer registered in `ConsumersRegistry` for one or all aliases.
Each consumer runs in its own thread sharing a single `stop_event`. `SIGTERM` and
`SIGINT` set the event for graceful shutdown; the command joins all threads before
returning.

| Option          | Description                                                     |
|-----------------|-----------------------------------------------------------------|
| `--using ALIAS` | Start consumers for the named alias only. Omit for all aliases. |

---

## Settings reference

Keys of each alias in `RABBITMQ_CONNECTIONS`:

| Key                          | Type                   | Required                    | Description                                                                                                     |
|------------------------------|------------------------|-----------------------------|-----------------------------------------------------------------------------------------------------------------|
| `HOST`                       | `str`                  | with `PORT`, or use `NODES` | Broker hostname or IP. Mutually exclusive with `NODES`.                                                         |
| `PORT`                       | `int`                  | with `HOST`, or use `NODES` | AMQP port (typically `5672`). Mutually exclusive with `NODES`.                                                  |
| `NODES`                      | `list[dict[str, Any]]` | or use `HOST` / `PORT`      | Non-empty list of nodes, each with `HOST` and `PORT`. Mutually exclusive with `HOST` / `PORT`.                  |
| `VIRTUAL_HOST`               | `str`                  | yes                         | Virtual host (e.g. `'/'`).                                                                                      |
| `USER`                       | `str`                  | yes                         | Authentication username.                                                                                        |
| `PASSWORD`                   | `str`                  | yes                         | Authentication password.                                                                                        |
| `HEARTBEAT`                  | `int`                  | yes                         | Heartbeat interval in seconds.                                                                                  |
| `BLOCKED_CONNECTION_TIMEOUT` | `int`                  | yes                         | Seconds before a blocked connection times out.                                                                  |
| `RECONNECT_INITIAL_BACKOFF`  | `float`                | yes                         | Initial consumer reconnect delay in seconds.                                                                    |
| `RECONNECT_MAX_BACKOFF`      | `float`                | yes                         | Maximum consumer reconnect delay (backoff cap).                                                                 |
| `SHUFFLE_NODES`              | `bool`                 | no (default `False`)        | Reshuffle the node order on every connection attempt.                                                           |
| `SOCKET_TIMEOUT`             | `float`                | no (default `10.0`)         | Seconds to wait for the TCP connection to one node. Positive number; `bool` and strings are rejected.           |
| `STACK_TIMEOUT`              | `float`                | no (default `15.0`)         | Seconds to wait for the full TCP + AMQP bring-up of one node. Positive number; `bool` and strings are rejected. |

Required keys: `VIRTUAL_HOST`, `USER`, `PASSWORD`, `HEARTBEAT`, `BLOCKED_CONNECTION_TIMEOUT`,
`RECONNECT_INITIAL_BACKOFF`, `RECONNECT_MAX_BACKOFF`. A missing key raises a `KeyError` during
`AppConfig.ready()`. Node addressing is required too: either `HOST` and `PORT`, or `NODES` (not both);
otherwise `ImproperlyConfigured` is raised. `SHUFFLE_NODES`, `SOCKET_TIMEOUT` and `STACK_TIMEOUT` are optional.

The optional global `RABBITMQ_HEALTHCHECK` setting is a dict; every key is optional and `{}` keeps all defaults:

| Key              | Type    | Default | Description                                                          |
|------------------|---------|---------|----------------------------------------------------------------------|
| `DEADLINE`       | `float` | `15.0`  | Overall budget in seconds for checking every alias.                  |
| `SOCKET_TIMEOUT` | `float` | `5.0`   | Seconds to wait for the TCP connection to one node during the probe. |
| `STACK_TIMEOUT`  | `float` | `10.0`  | Seconds to wait for the full TCP + AMQP bring-up of one node.        |

See [Configuration](./configuration.md) for a full settings example.
