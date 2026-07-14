---
title: Reliability
order: 9
---

# Reliability

Django-RMQ is built around an **at-least-once** delivery guarantee. Every design
decision in the library serves one goal: a message that was accepted by `publish()`
must eventually reach a handler, and a handler failure must never cause silent message
loss.

This page describes each reliability mechanism, where it lives in the code, and what
you need to do (or not do) in your own code to benefit from it.

---

## Publisher confirms

Every producer channel has publisher confirms enabled. The channel is opened with
`confirm_delivery()` so every `basic_publish` call blocks until the broker
acknowledges the message:

```python
# django_rmq/connections.py
channel.confirm_delivery()
```

This means `Producer.publish()` is synchronous with respect to broker acceptance.
If the broker cannot accept the message — for example, because no queue matches the
routing key — it raises `pika.exceptions.UnroutableError` rather than silently
dropping the message.

---

## Mandatory routing

`basic_publish` is always called with `mandatory=True`:

```python
# django_rmq/producer.py
channel.basic_publish(
    exchange=self.exchange,
    routing_key=routing_key,
    body=body,
    properties=properties,
    mandatory=True,
)
```

Together with publisher confirms this guarantees that publishing to a routing key
that matches no bound queue raises `UnroutableError` immediately. The integration
test suite verifies this against a real broker:

```python
from django_rmq.producer import Producer
from pika.exceptions import UnroutableError

# Publishing to the default exchange with a routing key that matches no queue
# raises UnroutableError (not a silent drop).
producer: Producer = Producer(exchange='', queue='')

with pytest.raises(UnroutableError):
    producer.publish(body=b'nowhere', routing_key='no-such-queue')
```

---

## Persistent messages

Every message published through `Producer.publish()` is marked persistent
(`delivery_mode=2`). If no `BasicProperties` are provided, the library creates
them with `delivery_mode=DeliveryMode.Persistent`. If you supply your own
`BasicProperties` without setting `delivery_mode`, the library forces it to
persistent as well:

```python
from django_rmq.producer import Producer
from pika.spec import BasicProperties

producer: Producer = Producer(queue='orders')

# delivery_mode is forced to 2 regardless of whether you pass properties or not.
producer.publish(body='{"order_id": 42}')

# Custom properties — delivery_mode will still be forced to 2.
props: BasicProperties = BasicProperties(content_type='application/json')
producer.publish(body='{"order_id": 42}', properties=props)
```

Persistent messages survive a broker restart, provided the queue is also durable.
A `QueueConfig` is durable by default; a plain string queue is declared durable
when consumed via `Consumer`.

---

## Producer self-heal (retry once)

When the cached producer channel or connection is broken at publish time, the
producer resets it and retries exactly once. The set of errors that trigger a
retry is fixed:

```python
# django_rmq/producer.py
_RECONNECTABLE_ERRORS = (
    AMQPConnectionError,
    ConnectionClosed,
    ChannelClosed,
    ChannelClosedByBroker,
    StreamLostError,
    ConnectionResetError,
)
```

On the first attempt, if one of these errors is raised, `reset_producer_channel()`
drops the cached channel and connection. The second attempt opens a fresh channel
and retries the same publish. If the retry also fails, the exception propagates to
the caller.

The integration test suite verifies this by force-closing the producer connection
via the Management API:

```python
from django_rmq.producer import Producer

producer: Producer = Producer(queue='orders')

producer.publish(body=b'first')   # opens the producer connection

# force-close the connection from outside...

producer.publish(body=b'second')  # transparently reconnects and succeeds
```

**Exactly one retry is made.** There is no loop or exponential backoff on the
producer side. If the broker is unreachable after the retry, the exception
propagates.

---

## Consumer reconnect with exponential backoff

The consumer reconnects automatically on any error in `_RECONNECTABLE_ERRORS`.
After each disconnect, the reconnect delay doubles until it reaches
`reconnect_max_backoff`:

```python
# django_rmq/consumer.py
backoff = min(backoff * 2, max_backoff)
```

The backoff values come from the connection alias config (`RECONNECT_INITIAL_BACKOFF`
and `RECONNECT_MAX_BACKOFF`). You can also override them per consumer:

```python
from django_rmq.consumer import Consumer
from django_rmq.queues.queue_config import QueueConfig

consumer: Consumer = Consumer(
    queue=QueueConfig(name='orders'),
    reconnect_initial_backoff=0.5,  # seconds; defaults to alias config value
    reconnect_max_backoff=60.0,     # seconds; defaults to alias config value
)
```

During a reconnect wait, `stop_event.wait(timeout=backoff)` is used so that
a shutdown signal wakes the consumer immediately instead of waiting out the full
backoff delay.

An unrecoverable error (any exception not in `_RECONNECTABLE_ERRORS`) is logged
at `error` level and re-raised, ending the consume loop.

---

## Dead-letter on handler failure

When a handler raises an exception, `Consumer._dispatch` logs the error and calls
`basic_nack(requeue=False)`:

```python
# django_rmq/consumer.py — _dispatch
try:
    handler(ch, method, props, body)
except Exception as exc:
    logger.error(...)
    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
```

`requeue=False` tells the broker to dead-letter the message instead of putting it
back on the queue. If the queue was declared with a `dead_letter_exchange`, the
message is routed there. Without a DLX the broker discards it.

This behavior is intentional: infinite requeue loops on a poison message can
saturate a queue and starve healthy consumers. Configure a DLX + DLQ for any
queue where you need to inspect failed messages.

See [Topology](/en/1.0.5/topology.html) for how to declare a dead-letter exchange with
`QueueConfig`.

**Your handler must explicitly acknowledge every successfully processed message.**
The library does not auto-ack. A missing `basic_ack` causes the message to remain
unacknowledged and be redelivered after the consumer disconnects.

```python
from typing import Any
from pika.adapters.blocking_connection import BlockingChannel

@consumer
def handle_order(
    ch: BlockingChannel,
    method: Any,
    props: Any,
    body: bytes,
) -> None:
    process(body)
    ch.basic_ack(delivery_tag=method.delivery_tag)  # required
```

The integration test verifies the full path — handler raises, broker routes to DLQ:

```python
from django_rmq.consumer import Consumer
from django_rmq.producer import Producer
from django_rmq.queues.queue_config import QueueConfig

queue_config: QueueConfig = QueueConfig(
    name='orders',
    dead_letter_exchange='dlx-orders',
    dead_letter_routing_key='dlq-orders',
)
consumer: Consumer = Consumer(queue=queue_config)

@consumer
def handler(ch: BlockingChannel, method: Any, props: Any, body: bytes) -> None:
    raise ValueError('boom')   # nacked -> routed to dlx-orders / dlq-orders

Producer(queue=queue_config).publish(body='{"will": "fail"}')
```

---

## Django DB connections

Consumer threads are long-lived. Django's database connection pool has server-side
idle timeouts; after a period of inactivity the server closes the socket but the
Django thread still holds a reference to the dead connection.

`Consumer._dispatch` calls `close_old_connections()` before every message dispatch:

```python
# django_rmq/consumer.py — _dispatch
from django.db import close_old_connections

close_old_connections()
try:
    handler(ch, method, props, body)
```

This forces Django to discard stale connections so the ORM re-establishes them
lazily on the next database query, preventing `OperationalError: server closed
the connection unexpectedly` in handlers.

---

## Thread-safety model

Django-RMQ uses `threading.local` to give each thread its own producer and consumer
connection:

```python
# django_rmq/connections.py
self._local: threading.local = threading.local()
```

The split between producer and consumer connections is intentional. A `BlockingConnection`
owns exactly one I/O loop. While `Consumer.consume()` drives that loop with
`process_data_events()`, any concurrent `publish()` on the same connection would
corrupt the AMQP protocol stream. Separate connections make the pattern of publishing
from inside a consumer handler safe by construction.

| Thread type      | Connection slot                                          | Notes                                                  |
|------------------|----------------------------------------------------------|--------------------------------------------------------|
| Consumer thread  | `_local.consumer_connection`                             | Owned by `_run_session`; closed on session end         |
| Any other thread | `_local.producer_connection` + `_local.producer_channel` | Created on first publish; reset on reconnectable error |

Do not share a `Producer` or `Consumer` instance across threads. Create one per
thread, or rely on the `start_consumers` management command which manages threading
for you.
