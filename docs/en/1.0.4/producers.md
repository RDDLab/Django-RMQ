---
title: Producers
order: 4
---

# Producers

A `Producer` publishes messages to RabbitMQ through a thread-local blocking channel. One instance is bound to a specific exchange and queue at creation time and reuses that binding for every call to `publish`.

## Creating a Producer

```python
from django_rmq.producer import Producer
from django_rmq.queues.queue_config import QueueConfig

# Default exchange, queue named by string
producer: Producer = Producer(queue='orders')

# Named exchange, no fixed queue (exchange-only mode)
producer: Producer = Producer(exchange='events', queue='')

# With a QueueConfig (carries dead-letter settings)
queue_config: QueueConfig = QueueConfig(
    name='orders',
    dead_letter_exchange='dlx-orders',
    dead_letter_routing_key='dlq-orders',
)
producer: Producer = Producer(queue=queue_config)

# Explicit connection alias (required when multiple connections are configured)
producer: Producer = Producer(queue='orders', using='payments')
```

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `exchange` | `str` | `''` | Exchange name. An empty string means the default (direct) exchange. |
| `queue` | `QueueConfig \| str` | `''` | Queue to publish to. Also used as the default routing key. Pass an empty string for exchange-only publishing with an explicit `routing_key`. |
| `using` | `str \| None` | `None` | Connection alias from `RABBITMQ_CONNECTIONS`. Omit when a single connection is configured. |

A `Producer` can be instantiated at module level — it does not open a connection on `__init__`. The connection and channel are obtained lazily on the first `publish` call.

## Publishing a Message

```python
import json
from django_rmq.producer import Producer

producer: Producer = Producer(queue='orders')

# String body — encoded to UTF-8 bytes automatically
producer.publish(body='{"order_id": 42}')

# Bytes body — passed through unchanged
producer.publish(body=b'{"order_id": 42}')

# Override routing key (exchange-only mode)
Producer(exchange='events', queue='').publish(
    body=json.dumps({'event': 'order.created'}),
    routing_key='payments.created',
)
```

**`publish` signature**

```python
def publish(
    self,
    body: str | bytes,
    routing_key: str | None = None,
    properties: BasicProperties | None = None,
) -> None: ...
```

- `body` — `str` is encoded to UTF-8; `bytes` is sent as-is.
- `routing_key` — if omitted, `self.queue` (the queue name) is used.
- `properties` — AMQP message properties; see [Custom Properties](#custom-properties) below.

## Persistent Delivery

Every message published by `Producer` is **persistent** (`delivery_mode=2`). This means the broker writes the message to disk and it survives a broker restart, provided the queue itself is durable.

If you pass a `BasicProperties` object without setting `delivery_mode`, the producer forces it to `DeliveryMode.Persistent`. The only way to send a transient message is to explicitly set `delivery_mode=DeliveryMode.Transient` in your properties object.

```python
from pika import DeliveryMode
from pika.spec import BasicProperties
from django_rmq.producer import Producer

# Explicitly transient (unusual — only if you know what you are doing)
Producer(queue='ephemeral').publish(
    body='ping',
    properties=BasicProperties(delivery_mode=DeliveryMode.Transient.value),
)
```

## Lazy Queue Declaration

The queue is declared on the broker **once, on the first `publish`** — not when the `Producer` is created. After that the `_is_queue_declared` flag prevents further declarations.

The declaration mode depends on the `queue` argument type:

| `queue` type | Declaration mode | Effect |
|---|---|---|
| `str` (non-empty) | `passive=True` | Verifies the queue exists; raises `ChannelClosedByBroker` (404) if it does not. |
| `QueueConfig` | Active declare with `durable` + `arguments` | Creates the queue if absent; idempotent if already present with the same parameters. |
| `''` (empty string) | Skipped entirely | Use explicit `routing_key`; producer goes straight to `basic_publish`. |

Use `QueueConfig` when the queue carries dead-letter arguments or when you want the producer to create the queue if it does not yet exist. Use a plain string when the queue is guaranteed to exist (declared by a setup function or another service).

## Reliability: Confirms, Mandatory, and Retry

**Publisher confirms** are enabled on every producer channel (`confirm_delivery()`). After each `basic_publish` the broker acknowledges the message. If no queue matches the routing key, the broker returns the message and pika raises `UnroutableError`.

**`mandatory=True`** is always set. A message published to an exchange with no matching binding is **not silently dropped** — the broker returns it and pika raises `UnroutableError`.

```python
from pika.exceptions import UnroutableError
from django_rmq.producer import Producer

producer: Producer = Producer(exchange='', queue='')

try:
    producer.publish(body=b'nowhere', routing_key='no-such-queue')
except UnroutableError:
    # The broker had no queue for this routing key.
    ...
```

**Retry on transient errors.** When `publish` encounters a reconnectable AMQP error (`AMQPConnectionError`, `ConnectionClosed`, `ChannelClosed`, `ChannelClosedByBroker`, `StreamLostError`, `ConnectionResetError`), it resets the cached channel and connection, then retries **exactly once**. If the retry also fails, the exception propagates to the caller.

Non-reconnectable exceptions (e.g. `ValueError`, `UnroutableError`) are not retried and propagate immediately.

## Producer as a Decorator

A `Producer` instance can decorate a function. The decorator publishes the function's return value automatically after the function runs.

```python
import json
from django_rmq.producer import Producer

order_producer: Producer = Producer(queue='orders')

@order_producer
def create_order(order_id: int) -> str:
    # business logic here
    return json.dumps({'order_id': order_id})

# Calling create_order publishes the returned JSON and also returns it.
result: str = create_order(order_id=42)
```

**Return value contract:**

| Return type | Behaviour |
|---|---|
| `str` or `bytes` | Published and returned to the caller. |
| `None` | Publishing is skipped; `None` is returned. |
| Any other type | `TypeError` is raised immediately. |

The strictness on other types is intentional — silently serializing a `dict` or `list` would hide contract errors.

## Exchange-Only Publishing

To publish to an exchange without a fixed queue (e.g. a fanout or topic exchange), set `queue=''` and always provide `routing_key` in `publish`:

```python
from django_rmq.producer import Producer

events_producer: Producer = Producer(exchange='domain.events', queue='')

events_producer.publish(
    body=b'{"type": "order.shipped", "order_id": 7}',
    routing_key='order.shipped',
)
```

No queue declaration is performed in this mode.

## Custom Properties

Pass a `BasicProperties` instance to override content type, headers, correlation ID, or other AMQP properties. `delivery_mode` is forced to `Persistent` unless you set it explicitly.

```python
from pika.spec import BasicProperties
from django_rmq.producer import Producer

Producer(queue='orders').publish(
    body=b'{"order_id": 1}',
    properties=BasicProperties(
        content_type='application/json',
        correlation_id='req-abc-123',
        headers={'x-source': 'checkout-service'},
    ),
)
```

## See Also

- [Topology](/en/1.0.4/topology.html) — declare exchanges and queues with `QueueConfig` and setup functions.
- [Reliability](/en/1.0.4/reliability.html) — full delivery model, confirms, and reconnect details.
- [Multiple Connections](/en/1.0.4/multiple-connections.html) — the `using` parameter.
- [API Reference](/en/1.0.4/api-reference.html) — complete `Producer` signature.
