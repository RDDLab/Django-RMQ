---
title: Management Commands
order: 8
---

# Management Commands

Django-RMQ ships three management commands. `setup_rabbitmq_topology` and `start_consumers` extend
`RDDBaseCommand`; `check_rabbitmq_connections` is a lightweight healthcheck that deliberately does not.

## `setup_rabbitmq_topology`

Declares all exchanges, queues, and bindings registered in the [SetupRegistry](/en/1.0.4/registries.html) for each connection
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

Starts all consumers registered in the [ConsumersRegistry](/en/1.0.4/registries.html). Each consumer runs in its own thread.
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

## `check_rabbitmq_connections`

A healthcheck command that verifies RabbitMQ connectivity. For each alias it opens a producer connection and closes it
immediately, reporting which aliases are reachable. The command exits non-zero if any connection fails, which makes it
suitable for readiness/liveness probes.

```bash
uv run python manage.py check_rabbitmq_connections
```

### Options

| Option    | Type  | Default | Description                                                                                                  |
|-----------|-------|---------|--------------------------------------------------------------------------------------------------------------|
| `--using` | `str` | `None`  | Connection alias from `RABBITMQ_CONNECTIONS` to check. When omitted, checks every configured alias.          |

### What it does

1. Verifies django_rmq is initialized — raises `ImproperlyConfigured` if `django_rmq` is not in `INSTALLED_APPS`.
2. Resolves the list of aliases (`--using` selects one; otherwise all configured aliases).
3. For each alias, opens a producer connection and closes it immediately:
   - On success, prints `OK: <alias>` (bold green) to stdout.
   - On failure (`AMQPError` or `OSError`), logs a warning and prints `FAIL: <alias>` to stderr.
4. If any alias failed, raises `CommandError` (exit code 1) listing the unhealthy aliases.
5. If all aliases are reachable, prints a final `ok: <aliases>` summary line.

### Example output

```
  OK: default
  OK: analytics
ok: default, analytics
```

On failure:

```
  OK: default
  FAIL: analytics
CommandError: unhealthy: analytics
```

### Example: checking a specific alias

```bash
uv run python manage.py check_rabbitmq_connections --using analytics
```

### Exit codes

| Code | Meaning                                                    |
|------|------------------------------------------------------------|
| `0`  | All checked aliases are reachable.                         |
| `1`  | At least one alias is unreachable (raises `CommandError`). |

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

Use `check_rabbitmq_connections` as a readiness/liveness probe — it exits non-zero when a broker is unreachable:

```yaml
livenessProbe:
  exec:
    command: ["uv", "run", "python", "manage.py", "check_rabbitmq_connections"]
  periodSeconds: 30
```
