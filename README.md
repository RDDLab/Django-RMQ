![Logo](docs/.vuepress/public/logo.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=for-the-badge)](https://docs.astral.sh/ruff)
[![PyPI](https://img.shields.io/pypi/v/django-rmq?style=for-the-badge)](https://pypi.org/project/django-rmq/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/django-rmq.svg?style=for-the-badge)](https://pypi.python.org/pypi/django-rmq/)
[![PyPI djversions](https://img.shields.io/pypi/djversions/django-rmq.svg?style=for-the-badge)](https://pypi.org/project/django-rmq/)
[![PyPI status](https://img.shields.io/pypi/status/django-rmq.svg?style=for-the-badge)](https://pypi.python.org/pypi/django-rmq)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/django-rmq?style=for-the-badge)](https://pypistats.org/packages/django-rmq)
[![PyPI - Types](https://img.shields.io/pypi/types/django-rmq.svg?style=for-the-badge)](https://pypi.python.org/pypi/django-rmq)
[![Tests](https://github.com/RDDLab/Django-RMQ/actions/workflows/ci.yml/badge.svg?branch=main&style=for-the-badge)](https://github.com/RDDLab/Django-RMQ/actions/workflows/ci.yml)

---

[![RabbitMQ Support](https://img.shields.io/static/v1?label=RabbitMQ%20Support&message=v3.13%20%7C%20v4.0%20%7C%20v4.1%20%7C%20v4.2%20%7C%20v4.3&color=ff6600&labelColor=555&style=for-the-badge)](https://www.rabbitmq.com/)

---

**Documentation**: <a href="https://django-rmq.rdd-lab.com/" target="_blank">https://django-rmq.rdd-lab.com/</a>

**Source Code**: <a href="https://github.com/RDDLab/Django-RMQ" target="_blank">https://github.com/RDDLab/Django-RMQ</a>

---

# Django-RMQ

TODO ...


---

## Testing

### Unit tests

Unit tests mock `pika` and need no broker. They run by default — integration
tests are marked `integration` and deselected:

```bash
uv run pytest
```

### Integration tests

Integration tests run against a **real** RabbitMQ broker. The repo ships a
`.github/docker-compose.yml` that starts the same image CI uses (with the
management plugin the suite needs on port `15672`). Connection params are read
from `RMQ_*` env vars (defaults: `localhost:5672`, `guest`/`guest`, vhost `/`),
which already match the Compose service:

```bash
docker compose -f .github/docker-compose.yml up -d --wait    # start the broker, block until healthy
uv run pytest -m integration
docker compose -f .github/docker-compose.yml down            # stop it when done
```

The suite isolates itself with per-test `uuid`-suffixed queues/exchanges and
cleans them up, so it is safe against a shared broker (use a dedicated vhost).

---