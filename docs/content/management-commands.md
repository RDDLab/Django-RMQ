---
title: Management Commands
sidebar_position: 8
---

Django-RMQ ships three management commands. `setup_rabbitmq_topology` and `start_consumers` extend
`RDDBaseCommand`; `check_rabbitmq_connections` is a lightweight healthcheck that deliberately does not.

## `setup_rabbitmq_topology`

Declares all exchanges, queues, and bindings registered in the [SetupRegistry](./registries.md) for each connection
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

Starts all consumers registered in the [ConsumersRegistry](./registries.md). Each consumer runs in its own thread.
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

A healthcheck command that verifies RabbitMQ connectivity. It probes every node of every alias in parallel (each probe
opens a connection and closes it immediately) with short timeouts from the `RABBITMQ_HEALTHCHECK`
setting. An alias is reachable if at least one of its nodes answered. The command finishes by its own deadline (15
seconds by default) and prints its result. It is designed for liveness/readiness probes: the output is one line per
event, written to stdout, never colored, and flushed after every line. If a probe is killed on timeout, the last
printed line shows the phase the process was in (see Diagnosing healthcheck timeouts).
The command exits with code `0` when every alias is reachable and `1` otherwise.

```bash
uv run python manage.py check_rabbitmq_connections
```

### Options

| Option          | Type             | Default                                       | Description                                                                                                                                                                                  |
|-----------------|------------------|-----------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--using`       | `str`            | `None`                                        | Connection alias from `RABBITMQ_CONNECTIONS` to check. When omitted, checks every configured alias.                                                                                          |
| `--format`      | `json` \| `text` | `text`                                        | Output format: logfmt-style `key=value` text, or one JSON object per line (JSON Lines).                                                                                                      |
| `--timeout`     | `float`          | `RABBITMQ_HEALTHCHECK['DEADLINE']` (`15.0`)   | Overall deadline in seconds for the whole check (all aliases). Must be greater than 0, otherwise `CommandError`. When it expires, aliases without a live node fail with `TimeoutError`.      |
| `--skip-checks` | flag             | `off`                                         | No-op, kept for backward compatibility. The command never runs Django system checks, so passing it changes nothing.                                                                          |

When calling the command from code, pass the format as `output_format` (not `format`) and the deadline as `timeout`.
The `--no-color` and `--force-color` options have no effect: the output is never colored. Django system checks are not
run by this command, either from the command line or via `call_command`.

### What it does

1. Skips Django system checks (`requires_system_checks = ()`): the probe runs in a new process on every call, and
   checks such as the URL configuration check would import the URLconf each time. Configuration errors are caught when
   the worker itself (`start_consumers`) starts.
2. Verifies django_rmq is initialized — raises `ImproperlyConfigured` if `django_rmq` is not in `INSTALLED_APPS`
   (nothing is printed in this case).
3. Validates `--timeout` (a value `<= 0` raises `CommandError`, nothing is printed) and determines the deadline:
   `--timeout` if given, otherwise `RABBITMQ_HEALTHCHECK['DEADLINE']`.
4. Determines the list of aliases (`--using` selects one; otherwise all configured aliases).
5. Prints the `startup` event.
6. Builds the connection parameters of every node with
   `RabbitMQConnectionManager.build_probe_parameters(socket_timeout=…, stack_timeout=…)`, using the timeouts from
   `RABBITMQ_HEALTHCHECK`. An unknown alias raises `ImproperlyConfigured` here: after `startup` is printed, before any
   thread is started.
7. Starts one daemon thread per node of all aliases at once. Each thread opens a connection to its node only and closes
   it. Any exception counts as a failure of that node.
8. Prints a `check` event as soon as an alias is decided:
   - An alias is `ok` as soon as its first node succeeds; the event contains that node.
   - An alias is `fail` when all of its nodes failed.
   - When the deadline expires, every alias that is still undecided fails with a `TimeoutError`.
9. Prints the `summary` event. In the text format, the `ERROR` lines follow it.
10. If any alias failed, exits with code 1 (see Exit codes). The probe threads are daemon threads, so
    nodes that hang do not hold the process and do not delay the exit.

The alias's own `SOCKET_TIMEOUT` and `STACK_TIMEOUT`, as well as `SHUFFLE_NODES`, are not used by this command: the
probe time must not depend on how the nodes are ordered or on the timeouts tuned for working connections (see
Node timeouts and failover time).

### Output events

| Event     | When                                                                | JSON fields                                                                                                  | Text form                                                                        |
|-----------|---------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| `startup` | Once, before any connection is opened                               | `seconds` (number or `null`)                                                                                 | `startup=8.71s` or `startup=unknown`                                             |
| `check`   | Once per alias, in completion order (not configuration order)       | `status` (`ok` / `fail`), `alias`, `seconds`, `node` (only on `ok`), `error` (only on `fail`)                | `OK alias=… node=… connect=…` or `FAIL alias=… took=…` + `ERROR alias=… error=…` |
| `summary` | Once, after all `check` events                                      | `status` (`healthy` / `unhealthy`), `healthy`, `total`, `failed` (list of aliases), `seconds`                | `HEALTHY aliases=2/2 total=…` or `UNHEALTHY failed=… aliases=1/2 total=…`        |

- **`startup.seconds`** — time from the start of the Python process to the beginning of the check: interpreter start,
  imports, and `django.setup()`. Django system checks are not run by this command, so they are not part of this time.
  It is read from `/proc`, so it is available on Linux only; elsewhere it is `null`
  (`unknown` in text). With `uv run`, the time spent by `uv` itself is not included.
- **`node`** — `host:port` of the node that answered first. It is useful with `NODES` in a
  [cluster setup](./clusters.md).
- **`error`** — the reason an alias failed, on a single line (whitespace is collapsed):
  - If all nodes failed: `<host>:<port> <ExceptionType>: <message>` for each node, joined by `; ` in the order the
    nodes failed. When an exception has no message, `repr()` of its arguments is used, or the bare type name if it has
    no arguments (for example, `rmq-1:5672 AMQPConnectionError`).
  - If the deadline expired: `TimeoutError: no node answered within <deadline>s`, followed by `; ` and the errors of
    the nodes that failed already, then `<host>:<port> no answer` for each node that did not answer, in `NODES` order.
    The deadline is printed compactly (`15`, `2`, `0.2`).
- **`seconds` of a `check`** (`connect` / `took` in text) — measured from the start of the check phase (all probes
  start together). For `ok` — until the first successful node finished connecting and closing; for `fail` — until the
  last node failed, or about the deadline if it expired.
- **`seconds` of the `summary`** (`total` in text) — `startup` plus the wall-clock duration of the check phase
  (only the check phase, if `startup` is unknown). Aliases run in parallel, so this is about the slowest alias, at most
  the deadline, not a sum. The time the process spends shutting down after the summary is not included.
- **Precision** — JSON durations are numbers rounded to milliseconds (`0.142`); text durations have two decimals and
  an `s` suffix (`0.14s`).

### Example output

With `--format json` every event is a JSON object, which is meant for log aggregators. Values below are illustrative.

All aliases are reachable:

```
{"event": "startup", "seconds": 8.712}
{"event": "check", "status": "ok", "alias": "default", "seconds": 0.142, "node": "rmq-2:5672"}
{"event": "check", "status": "ok", "alias": "analytics", "seconds": 0.018, "node": "rmq-1:5672"}
{"event": "summary", "status": "healthy", "healthy": 2, "total": 2, "failed": [], "seconds": 8.874}
```

One alias is unreachable:

```
{"event": "startup", "seconds": 1.204}
{"event": "check", "status": "ok", "alias": "default", "seconds": 0.021, "node": "rmq-2:5672"}
{"event": "check", "status": "fail", "alias": "analytics", "seconds": 0.048, "error": "rmq-1:5672 AMQPConnectionError: (AMQPConnectorSocketConnectError: ConnectionRefusedError(111, 'Connection refused'),); rmq-2:5672 AMQPConnectionError: (AMQPConnectorSocketConnectError: ConnectionRefusedError(111, 'Connection refused'),)"}
{"event": "summary", "status": "unhealthy", "healthy": 1, "total": 2, "failed": ["analytics"], "seconds": 1.273}
```

Here `analytics` is a two-node cluster alias and both nodes refused the connection, so the error lists both of them.

Text is the default format: the same events are printed as human-readable `key=value` lines, which is convenient, for
example, in `docker inspect` output:

```
startup=8.71s
OK alias=default node=rmq-2:5672 connect=0.14s
OK alias=analytics node=rmq-1:5672 connect=0.02s
HEALTHY aliases=2/2 total=8.87s
```

```
startup=1.20s
OK alias=default node=rmq-2:5672 connect=0.02s
FAIL alias=analytics took=0.05s
UNHEALTHY failed=analytics aliases=1/2 total=1.27s
ERROR alias=analytics error="rmq-1:5672 AMQPConnectionError: (AMQPConnectorSocketConnectError: ConnectionRefusedError(111, 'Connection refused'),); rmq-2:5672 AMQPConnectionError: (AMQPConnectorSocketConnectError: ConnectionRefusedError(111, 'Connection refused'),)"
```

The deadline expired (an alias still had nodes that did not answer, so it fails with a `TimeoutError`):

```
startup=1.20s
OK alias=default node=rmq-2:5672 connect=0.02s
FAIL alias=analytics took=15.00s
UNHEALTHY failed=analytics aliases=1/2 total=16.22s
ERROR alias=analytics error="TimeoutError: no node answered within 15s; rmq-1:5672 AMQPConnectionError: (AMQPConnectorSocketConnectError: ConnectionRefusedError(111, 'Connection refused'),); rmq-2:5672 no answer"
```

A dead first node does not delay the verdict. Here the first entry of `NODES` is a black hole (packets are dropped),
the second node is alive, and the alias is `ok` as soon as the live node answers:

```
startup=1.20s
OK alias=default node=localhost:5672 connect=0.01s
HEALTHY aliases=1/1 total=1.21s
```

In text output a value is wrapped in double quotes when it is empty or contains a space, `"`, `=`, `\`, a tab, or a
newline; inside the quotes `\` and `"` are escaped with a backslash. For example:
`ERROR alias=default error="OSError: connection \"refused\""`. In the `UNHEALTHY` line, the failed aliases are
comma-separated without spaces and come before `aliases=`.

Text output puts the most important information first, so it survives when the probe output is truncated (for example,
by a length limit on stored healthcheck output): `FAIL` lines are short and carry no error message, and the error
messages — which can be long — are printed after the summary as `ERROR` lines, one per failed alias, in the same order
as the `check` lines (completion order). In JSON the error stays in the `check` event and the `summary` is the last
line.

For an unhealthy result the command never prints a `CommandError: ...` line. An invalid `--timeout` is the exception:
Django prints `CommandError: --timeout must be …` to stderr and the process exits with code 1.

### Example: checking a specific alias

```bash
uv run python manage.py check_rabbitmq_connections --using analytics
uv run python manage.py check_rabbitmq_connections --using analytics --format json
uv run python manage.py check_rabbitmq_connections --timeout 5
```

### Calling from code

```python
from django.core.management import call_command
from django.core.management.base import CommandError

try:
    call_command('check_rabbitmq_connections', using='analytics', output_format='text', timeout=5.0)
except CommandError as exc:
    print(exc)  # unhealthy: analytics
```

Events are still printed to the command's stdout. The `CommandError` message lists only the unreachable aliases,
separated by `", "`. If `timeout <= 0`, the command raises
`CommandError('--timeout must be a positive number of seconds, got …')` before printing anything.

### Exit codes

| Code | Meaning                                                                                                                                                                                                          |
|------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `0`  | All checked aliases are reachable (`summary.status` is `healthy`).                                                                                                                                               |
| `1`  | At least one alias is unreachable (`summary.status` is `unhealthy`). From the command line the process exits with code 1 without a `CommandError` line; via `call_command` it raises `CommandError('unhealthy: <aliases>')`. |

If django_rmq is not initialized, or `--using` names an unknown alias, Django raises `ImproperlyConfigured`: the process
exits with a non-zero code and a traceback, and no `summary` is printed. With an unknown alias the `startup` line may
already be printed.

An invalid `--timeout` (`0` or negative) raises `CommandError`: Django prints `CommandError: --timeout must be …` to
stderr and the process exits with code 1; nothing is written to stdout. A non-numeric value is rejected by the
argument parser (usage error, exit code 2).

### Logging

The command writes to the `rabbitmq` logger with `source` set to `check_rabbitmq_connections`. Logs are not mixed with
the command output; they follow your project's `LOGGING` configuration.

| Outcome       | Level     | `message`                      | `data`                              |
|---------------|-----------|--------------------------------|-------------------------------------|
| Node answered | `debug`   | `RabbitMQ node probe OK`       | `alias`, `node`, `seconds`          |
| Node failed   | `warning` | `RabbitMQ node probe failed`   | `alias`, `node`, `error`, `seconds` |
| Alias failed  | `warning` | `RabbitMQ connection failed`   | `alias`, `error`, `seconds`         |

- A node warning can appear even when the alias is `ok`: another node answered, but this node's thread finished before
  the process exited. It does not mean the alias failed.
- The `error` of a node log is that node's own error (without the `host:port` prefix); the `error` of an alias log is
  the combined string described in [Output events](#output-events).
- Node warnings precede the alias warning. `seconds` is rounded to 3 decimal places.

### Diagnosing healthcheck timeouts

Previously, a probe that exceeded its timeout left only a generic timeout message, and it was impossible to tell where
the time went. Now every line is printed and flushed immediately, so the last visible line shows the phase the process
was in.

Since 1.1.0 the command also bounds the check phase by its own deadline: instead of being killed by the orchestrator, it
prints `UNHEALTHY` with a `TimeoutError` and exits. This works only if the probe timeout is not less than `startup` +
`DEADLINE` (see Healthcheck timing budget).

| Last printed line   | Where the time went                                                                                                |
|---------------------|--------------------------------------------------------------------------------------------------------------------|
| *(nothing)*         | Python and Django were still starting (interpreter, imports, `django.setup()`); with `uv run` — also `uv` itself. |
| `startup`           | No alias is decided yet: all nodes of all aliases are still connecting (see the remedy below the table).           |
| some `check` lines  | Aliases missing from the printed lines (compare with your configuration) were still waiting for a node.            |
| `summary` / `ERROR` | Process shutdown after the check (`atexit` handlers, non-daemon threads of your project; not the probe threads).   |

If the last line is `startup` or a `check` line and the probe was killed, the probe timeout is less than `startup` +
`DEADLINE`: the command would have stopped itself at the deadline. Raise the probe timeout or lower `DEADLINE` /
`--timeout`.

How to read the numbers:

- A large `startup` means the time goes into starting Django, not into the broker. Increase the probe timeout or speed
  up the startup. System checks are already excluded, so the remaining time is interpreter start, imports and
  `django.setup()` (including your apps' `AppConfig.ready()`).
- `seconds` of an `ok` `check` is the time of the fastest node (see `node`).
- A `fail` with `took` close to `DEADLINE` and a `TimeoutError` means no node answered within the deadline; the nodes
  marked `no answer` hung (packets are dropped, or the handshake never completes).
- A `fail` with `took` below `DEADLINE` means all nodes returned errors: read the per-node errors.
- As a rule of thumb, `took` close to the probe `SOCKET_TIMEOUT` means packets are dropped (host down, firewall,
  partition); `took` close to the probe `STACK_TIMEOUT` means the node accepts TCP but the AMQP handshake hangs. For
  example, a black-holed node plus a refused port with the default `SOCKET_TIMEOUT` of 5 seconds gave `took=5.01s`.

Whether the partial output of a probe killed on timeout is kept depends on the orchestrator. To see it reliably, run the
command manually inside the container:

```bash
docker exec <container> /app/.venv/bin/python /app/manage.py check_rabbitmq_connections --format text
```

For a quick manual check with a short deadline, add `--timeout 2`:

```bash
docker exec <container> /app/.venv/bin/python /app/manage.py check_rabbitmq_connections --format text --timeout 2
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

Use `check_rabbitmq_connections` as a readiness/liveness probe — it exits non-zero when a broker is unreachable.

### Healthcheck timing budget

The probe timeout in your orchestrator must cover the whole run of the command:

```
probe timeout >= startup + DEADLINE + margin
```

`startup` is the Python and Django start time (see the `startup` event), `DEADLINE` is
`RABBITMQ_HEALTHCHECK['DEADLINE']` or `--timeout`. The defaults are chosen for a probe timeout of 25 seconds: up to
about 8 seconds for startup, 15 seconds of `DEADLINE`, and a margin. If the probe timeout is shorter, the orchestrator
kills the command before it can print `UNHEALTHY` with the reason.

This budget came from a real incident: a worker with a cluster alias and `SHUFFLE_NODES` was killed by its Docker
healthcheck with the 10-second timeout although RabbitMQ was fine. Each unreachable node cost 10–15 seconds, and
because the node order was random, the probe failed intermittently. The probe timeout was raised from 10 to 25
seconds; the probe command itself did not change.

If you cannot raise the probe timeout (for example, a strict `timeoutSeconds` in Kubernetes), lower the deadline and
the per-node timeouts instead, in `RABBITMQ_HEALTHCHECK` or with `--timeout`. Example values:

```python
RABBITMQ_HEALTHCHECK = {
    'DEADLINE': 8.0,
    'SOCKET_TIMEOUT': 3.0,
    'STACK_TIMEOUT': 6.0,
}
```

Keep the per-node timeouts not greater than `DEADLINE`: otherwise a hanging node is reported as `no answer` instead of
with its own error. See `RABBITMQ_HEALTHCHECK` for all keys.

Recommendations:

- Run the virtualenv interpreter directly (`/app/.venv/bin/python`) instead of `uv run`. `uv run` checks the
  environment before every launch, which adds a delay to each probe call that is not reflected in `startup`.
- If a probe has to keep using `uv run`, add `--no-sync` (`uv run --no-sync python manage.py check_rabbitmq_connections`)
  or set `UV_NO_SYNC=1` in the container environment: uv then does not update the lockfile and does not sync the
  environment on each call. Starting `uv` itself still costs time that is not reflected in `startup`, so the virtualenv
  interpreter remains the preferred option.
- Passing `--skip-checks` is no longer needed: the command never runs Django system checks. The flag is still accepted,
  so existing probe definitions keep working.
- Set the probe timeout with a margin for Django startup and the deadline: see the
  Healthcheck timing budget. Use the `startup` value from the real output in your
  environment plus `DEADLINE` as a guide.
- In Kubernetes, set `timeoutSeconds` explicitly: the default is 1 second, which is almost always less than the time
  Django needs to start.
- `/app` is an example path; match it to your `WORKDIR`.

**Kubernetes (example):**

```yaml
livenessProbe:
  exec:
    command: ["/app/.venv/bin/python", "/app/manage.py", "check_rabbitmq_connections"]
  periodSeconds: 30
  timeoutSeconds: 25
  failureThreshold: 3
```

**Docker Compose (example):**

```yaml
services:
  worker:
    command: ["uv", "run", "python", "manage.py", "start_consumers"]
    healthcheck:
      test: ["CMD", "/app/.venv/bin/python", "/app/manage.py", "check_rabbitmq_connections", "--format", "text"]
      interval: 30s
      timeout: 25s
      retries: 3
      start_period: 30s
```

The timeout values are rough guides (see Healthcheck timing budget). `--format text` is convenient when reading the probe output stored by Docker, for
example via `docker inspect --format '{{json .State.Health}}' <container>`. See also
Diagnosing healthcheck timeouts.
