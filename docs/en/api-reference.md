---
title: API Reference
order: 12
---

# API Reference

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
from django_rmq.queues.queue_config import QueueConfig
```

Frozen dataclass for declarative queue configuration.

```python
@dataclass(frozen=True)
class QueueConfig:
    name: str
    durable: bool = True
    dead_letter_exchange: str | None = None
    dead_letter_routing_key: str | None = None
```

| Field                     | Type          | Default  | Description                                                               |
|---------------------------|---------------|----------|---------------------------------------------------------------------------|
| `name`                    | `str`         | required | Queue name. Also used as `str(queue_config)`.                             |
| `durable`                 | `bool`        | `True`   | Queue survives broker restarts.                                           |
| `dead_letter_exchange`    | `str \| None` | `None`   | Exchange dead-lettered messages are routed to (`x-dead-letter-exchange`). |
| `dead_letter_routing_key` | `str \| None` | `None`   | Routing key for dead-lettered messages (`x-dead-letter-routing-key`).     |

### `QueueConfig.arguments` property

```python
@property
def arguments(self) -> dict[str, Any] | None
```

Builds the AMQP `arguments` dict for queue declaration from the dead-letter
fields. Returns `None` when neither field is set.

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
    host: str
    port: int
    virtual_host: str
    user: str
    password: str
    heartbeat: int
    blocked_connection_timeout: int
    reconnect_initial_backoff: float
    reconnect_max_backoff: float
```

| Field                        | Type    | Description                                                    |
|------------------------------|---------|----------------------------------------------------------------|
| `host`                       | `str`   | Broker hostname or IP.                                         |
| `port`                       | `int`   | AMQP port.                                                     |
| `virtual_host`               | `str`   | Virtual host to connect to.                                    |
| `user`                       | `str`   | Username for `PlainCredentials`.                               |
| `password`                   | `str`   | Password for `PlainCredentials`.                               |
| `heartbeat`                  | `int`   | Heartbeat interval in seconds.                                 |
| `blocked_connection_timeout` | `int`   | Seconds to wait while the connection is blocked by the broker. |
| `reconnect_initial_backoff`  | `float` | Initial consumer reconnect delay in seconds.                   |
| `reconnect_max_backoff`      | `float` | Maximum consumer reconnect delay (exponential backoff cap).    |

---

## RabbitMQConnectionManager

```python
from django_rmq.connections import RabbitMQConnectionManager
```

Manages thread-local connections for producer and consumer roles. Instantiated
once per alias by `RabbitMQAppConfig.ready()`.

### `RabbitMQConnectionManager.__init__`

```python
def __init__(self, config: RabbitMQConfig) -> None
```

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

Returns the thread-local producer channel with publisher confirms enabled
(`confirm_delivery()`). Creates it on first call; reuses while open.

### `RabbitMQConnectionManager.reset_producer_channel`

```python
def reset_producer_channel(self) -> None
```

Closes and discards the cached producer channel and connection. Called
automatically by `Producer.publish` after a reconnectable error so the next
publish opens a fresh channel. Safe to call even when no channel is cached.

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
`setup_registries`, and `consumers_registries`.

**Raises:** `ImproperlyConfigured` — `RABBITMQ_CONNECTIONS` is missing or empty.

---

## Module globals (`django_rmq`)

```python
import django_rmq

django_rmq.connection_managers  # dict[str, RabbitMQConnectionManager] | None
django_rmq.setup_registries  # dict[str, SetupRegistry] | None
django_rmq.consumers_registries  # dict[str, ConsumersRegistry] | None
```

All three are `None` until `RabbitMQAppConfig.ready()` runs. Use the accessor
functions (`get_connection_manager`, `get_consumers_registry`, `get_setup_registry`)
rather than accessing these dicts directly.

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

| Key                          | Type    | Description                                     |
|------------------------------|---------|-------------------------------------------------|
| `HOST`                       | `str`   | Broker hostname or IP.                          |
| `PORT`                       | `int`   | AMQP port (typically `5672`).                   |
| `VIRTUAL_HOST`               | `str`   | Virtual host (e.g. `'/'`).                      |
| `USER`                       | `str`   | Authentication username.                        |
| `PASSWORD`                   | `str`   | Authentication password.                        |
| `HEARTBEAT`                  | `int`   | Heartbeat interval in seconds.                  |
| `BLOCKED_CONNECTION_TIMEOUT` | `int`   | Seconds before a blocked connection times out.  |
| `RECONNECT_INITIAL_BACKOFF`  | `float` | Initial consumer reconnect delay in seconds.    |
| `RECONNECT_MAX_BACKOFF`      | `float` | Maximum consumer reconnect delay (backoff cap). |

All nine keys are required for every alias. Missing keys raise a `KeyError` during
`AppConfig.ready()`. See [Configuration](/en/configuration.html) for a full
settings example.
