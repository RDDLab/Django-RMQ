# Django-RMQ

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://docs.astral.sh/ruff)
[![PyPI version](https://badge.fury.io/py/django-rmq.svg)](https://pypi.python.org/pypi/django-rmq/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/django-rmq.svg)](https://pypi.python.org/pypi/django-rmq/)
[![PyPI djversions](https://img.shields.io/pypi/djversions/django-rmq.svg)](https://pypi.org/project/django-rmq/)
[![PyPI status](https://img.shields.io/pypi/status/django-rmq.svg)](https://pypi.python.org/pypi/django-rmq)
[![PyPI - Types](https://img.shields.io/pypi/types/django-rmq.svg)](https://pypi.python.org/pypi/django-rmq)
[![Tests](https://github.com/RDDLab/Django-RMQ/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/RDDLab/Django-RMQ/actions/workflows/ci.yml)

---------------------------------------------------------------------------------------------------

[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-4%2B-blue)](https://www.rabbitmq.com/)

---------------------------------------------------------------------------------------------------

## Testing

Unit tests mock `pika` and need no broker. They run by default — integration
tests are marked `integration` and deselected:

```bash
uv run pytest
```

Integration tests run against a **real** RabbitMQ broker. The repo ships a
`docker-compose.yml` that starts the same image CI uses (with the management
plugin the suite needs on port `15672`). Connection params are read from
`RMQ_*` env vars (defaults: `localhost:5672`, `guest`/`guest`, vhost `/`),
which already match the Compose service:

```bash
docker compose up -d --wait    # start the broker, block until healthy
uv run pytest -m integration
docker compose down            # stop it when done
```

The suite isolates itself with per-test `uuid`-suffixed queues/exchanges and
cleans them up, so it is safe against a shared broker (use a dedicated vhost).

---------------------------------------------------------------------------------------------------