---
title: Тестирование
order: 11
---

# Тестирование

Набор тестов разделён на **юнит-тесты** (брокер не требуется, pika замокан) и **интеграционные тесты** (требуют живой
брокер RabbitMQ). Оба вида находятся в директории `tests/`.

---

## Юнит-тесты

Юнит-тесты мокируют `pika.BlockingConnection` в точке импорта в `connections.py`, поэтому реальный брокер не нужен. По
умолчанию запускаются именно они, поскольку интеграционные тесты помечены маркером и исключены в `pyproject.toml`:

```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = '-ra -m "not integration"'
markers = [
    "integration: tests that require a real RabbitMQ broker (deselected by default)",
]
```

Запуск юнит-тестов:

```bash
uv run pytest
```

---

## Интеграционные тесты

Интеграционные тесты помечены маркером `pytest.mark.integration`. Для них требуется запущенный брокер RabbitMQ с
включённым плагином управления (порт `15672`).

В репозитории есть Compose-файл, запускающий тот же образ, что используется в CI:

```bash
# Start the broker and wait until healthy.
docker compose -f .github/docker-compose.yml up -d --wait

# Run only integration tests.
uv run pytest -m integration

# Stop the broker when done.
docker compose -f .github/docker-compose.yml down
```

### Переменные окружения

Параметры подключения для интеграционных тестов считываются из переменных окружения `RMQ_*`. Значения по умолчанию
соответствуют Compose-сервису, поэтому для локального запуска дополнительная конфигурация не нужна:

| Переменная      | По умолчанию | Описание                     |
|-----------------|--------------|------------------------------|
| `RMQ_HOST`      | `localhost`  | Хостнейм брокера             |
| `RMQ_PORT`      | `5672`       | AMQP-порт                    |
| `RMQ_VHOST`     | `/`          | Виртуальный хост             |
| `RMQ_USER`      | `guest`      | Имя пользователя             |
| `RMQ_PASSWORD`  | `guest`      | Пароль                       |
| `RMQ_HEARTBEAT` | `30`         | Интервал heartbeat (секунды) |
| `RMQ_MGMT_PORT` | `15672`      | Порт Management API          |

Для запуска тестов против другого брокера задайте нужные переменные:

```bash
RMQ_HOST=rmq.staging.internal RMQ_USER=ci RMQ_PASSWORD=secret \
    uv run pytest -m integration
```

### Изоляция

Каждый интеграционный тест получает уникальные, не конфликтующие имена очередей и обменников с суффиксом UUID через
фикстуру `names`. Все объявленные ресурсы удаляются при завершении теста, поэтому набор безопасен при работе с общим
брокером. Тем не менее в CI рекомендуется использовать выделенный виртуальный хост.

---

## Тестирование собственных продюсеров и консьюмеров

### Мокирование pika в юнит-тестах

Фикстура `patch_blocking_connection` из `tests/conftest.py` заменяет `pika.BlockingConnection` на `MagicMock`.
Используйте аналогичный подход в собственных тестовых файлах:

```python
from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from django_rmq.connections import RabbitMQConnectionManager
from django_rmq.dto.rabbitmq_config import RabbitMQConfig


@pytest.fixture
def mock_channel() -> MagicMock:
    channel: MagicMock = MagicMock(name='BlockingChannel')
    channel.is_open = True
    return channel


@pytest.fixture
def mock_connection(mock_channel: MagicMock) -> MagicMock:
    connection: MagicMock = MagicMock(name='BlockingConnection')
    connection.is_open = True
    connection.channel.return_value = mock_channel
    return connection


@pytest.fixture
def patch_blocking_connection(mocker: MockerFixture, mock_connection: MagicMock) -> MagicMock:
    mocker.patch(
        target='django_rmq.connections.BlockingConnection',
        return_value=mock_connection,
    )
    return mock_connection
```

С установленным патчем вызовы `Producer.publish()` направляются в мок-канал, что позволяет проверять опубликованные
данные:

```python
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from django_rmq.producer import Producer


class TestMyProducer:
    def test_publish_sends_body(
        self,
        patch_blocking_connection: MagicMock,
        mock_channel: MagicMock,
    ) -> None:
        producer: Producer = Producer(queue='orders')
        producer.publish(body='{"order_id": 1}')

        mock_channel.basic_publish.assert_called_once()
        _, kwargs = mock_channel.basic_publish.call_args
        assert kwargs['routing_key'] == 'orders'
        assert kwargs['body'] == b'{"order_id": 1}'
        assert kwargs['mandatory'] is True
```

### Изолированное тестирование обработчика консьюмера

Обработчик — это обычный вызываемый объект. Его можно тестировать напрямую, передавая мок-объекты для канала, метода и
свойств:

```python
from typing import Any
from unittest.mock import MagicMock

from myapp.consumers import handle_order


class TestHandleOrder:
    def test_acks_on_success(self) -> None:
        ch: MagicMock = MagicMock()
        method: MagicMock = MagicMock()
        method.delivery_tag = 42
        props: MagicMock = MagicMock()

        handle_order(ch=ch, method=method, props=props, body=b'{"order_id": 1}')

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
```

### Сброс состояния django_rmq между тестами

`RabbitMQAppConfig.ready()` сохраняет реестры для каждого псевдонима как атрибуты модуля `django_rmq`. Тесты,
регистрирующие консьюмеры или функции настройки, мутируют глобальное состояние. Фикстура `reset_rmq_state` в
`tests/conftest.py` повторно запускает `ready()` при завершении каждого теста, автоматически восстанавливая чистое
базовое состояние (она применяется как `autouse=True`).

Если вашему набору тестов нужна аналогичная изоляция, добавьте похожую фикстуру в свой `conftest.py`:

```python
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def reset_rmq_state() -> Iterator[None]:
    yield
    from django.apps import apps as django_apps

    django_apps.get_app_config('django_rmq').ready()
```

---

## Добавление тестов

Соглашения проекта по написанию тестов — типизация, стиль импортов и паттерны фикстур — описаны
в [Руководстве по участию](/ru/1.0.4/contrib.html).
