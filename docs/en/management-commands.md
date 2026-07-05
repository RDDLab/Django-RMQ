---
title: Management Commands
order: 8
---

# Management Commands

Django-RMQ ships two management commands. Both extend `RDDBaseCommand`.

## `setup_rabbitmq_topology`

Declares all exchanges, queues, and bindings registered in the [SetupRegistry](/en/registries.html) for each connection
alias. The operation is idempotent and safe to run on every deploy.

```bash
uv run python manage.py setup_rabbitmq_topology
```

### Options

| Option    | Type  | Default | Description                                                                                                  |
|-----------|-------|---------|--------------------------------------------------------------------------------------------------------------|
| `--using` | `str` | `None`  | Connection alias from `RABBITMQ_CONNECTIONS` to set up. When omitted, runs setup for every configured alias. |

### What it does

For each alias the command:

1. Opens a producer connection and creates a channel.
2. Wraps the channel in `RecordingChannel` — a transparent proxy that intercepts `exchange_declare`, `queue_declare`,
   and `queue_bind` calls to record what was declared.
3. Calls `SetupRegistry.run_all(channel)` which executes every registered `SetupFn` in registration order.
4. Closes the channel.
5. Prints a topology report — exchanges, queues, and bindings declared during the run (de-duplicated by name).

### Example output

```
RabbitMQ setup complete for alias 'default'
  Exchanges (1):
    - orders [direct]
  Queues (2):
    - orders
    - orders.dlx {'x-dead-letter-exchange': 'dlx'}
  Bindings (1):
    - orders --[orders]--> orders
```

### Example: running for a specific alias

```bash
uv run python manage.py setup_rabbitmq_topology --using analytics
```

### Idempotency

RabbitMQ topology declarations (exchange/queue declare, queue bind) are passive-safe when the arguments match the
existing entity. Running the command multiple times on the same broker does not raise errors and does not change
already-declared topology. This makes it safe to include in deployment pipelines.

The full integration test that verifies this:

```python
from django.core.management import call_command
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType

from django_rmq.registries.setup_registry import get_setup_registry


def setup(channel: BlockingChannel) -> None:
    channel.exchange_declare(exchange='orders', exchange_type=ExchangeType.direct, durable=True)
    channel.queue_declare(queue='orders', durable=True)
    channel.queue_bind(queue='orders', exchange='orders', routing_key='rk')


get_setup_registry().register(fn=setup)

call_command('setup_rabbitmq_topology')

# Second call must not raise.
call_command('setup_rabbitmq_topology')
```

## `start_consumers`

Starts all consumers registered in the [ConsumersRegistry](/en/registries.html). Each consumer runs in its own thread.
The command blocks until a `SIGTERM` or `SIGINT` signal is received, then waits for all threads to finish before
exiting.

```bash
uv run python manage.py start_consumers
```

### Options

| Option    | Type  | Default | Description                                                                                                       |
|-----------|-------|---------|-------------------------------------------------------------------------------------------------------------------|
| `--using` | `str` | `None`  | Connection alias from `RABBITMQ_CONNECTIONS` to start. When omitted, starts consumers for every configured alias. |

### What it does

1. Resolves the list of aliases (`--using` selects one; otherwise all configured aliases).
2. Collects all consumers registered for those aliases via `ConsumersRegistry.all()`.
3. Prints a consumer table grouped by alias, showing queue name, prefetch count, and handler name.
4. Installs `SIGTERM` and `SIGINT` handlers that set a shared `threading.Event`.
5. Spawns one `threading.Thread` per consumer, each calling `consumer.consume(stop_event=stop_event)`.
6. Joins all threads — blocks until every thread has returned.

When no consumers are registered, the command logs a warning and exits immediately without blocking.

### Consumer table

Before starting threads the command prints a summary:

```
Consumers
Alias: default
  ├─ queue=orders  prefetch_count=5  handler=handle_order — Is consuming...
  └─ queue=notifications  prefetch_count=1  handler=handle_notification — Is consuming...
```

### Graceful shutdown

Send `SIGTERM` (or press `Ctrl-C` for `SIGINT`) to initiate shutdown. The signal handler sets the shared stop event;
each consumer thread exits its `basic_consume` loop when the event is detected. The command waits for all threads to
join before returning.

```bash
# In another terminal or from an orchestrator:
kill -TERM <pid>
```

### Example: running for a specific alias

```bash
uv run python manage.py start_consumers --using analytics
```

## Running in production

A typical production setup runs `setup_rabbitmq_topology` once during deployment, then keeps `start_consumers` running
as a long-lived process managed by a process supervisor (systemd, Docker, Kubernetes, etc.).

**systemd unit (example):**

```ini
[Unit]
Description = Django RMQ Consumers
After = network.target

[Service]
WorkingDirectory = /app
ExecStartPre = uv run python manage.py setup_rabbitmq_topology
ExecStart = uv run python manage.py start_consumers
Restart = on-failure
KillSignal = SIGTERM
TimeoutStopSec = 30

[Install]
WantedBy = multi-user.target
```

**Docker (example):**

```dockerfile
CMD ["uv", "run", "python", "manage.py", "start_consumers"]
```

Run `setup_rabbitmq_topology` as a separate init container or deployment hook so topology is always declared before
consumers try to bind to queues.
