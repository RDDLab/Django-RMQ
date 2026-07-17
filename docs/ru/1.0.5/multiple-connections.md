---
title: Несколько подключений
order: 10
---

# Несколько подключений

Django-RMQ поддерживает произвольное количество подключений RabbitMQ в одном Django-проекте. Каждое подключение
идентифицируется ключом-**псевдонимом** в `RABBITMQ_CONNECTIONS`. Параметр `using` в `Producer`, `Consumer` и
функциях-аксессорах определяет, какое подключение использовать.

---

## Настройка нескольких псевдонимов

Добавьте по одной записи на каждый брокер (или виртуальный хост) в `RABBITMQ_CONNECTIONS`:

```python
# settings.py
RABBITMQ_CONNECTIONS: dict = {
    'default': {
        'HOST': 'rmq-primary.internal',
        'PORT': 5672,
        'VIRTUAL_HOST': '/',
        'USER': 'app',
        'PASSWORD': 'secret',
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    },
    'analytics': {
        'HOST': 'rmq-analytics.internal',
        'PORT': 5672,
        'VIRTUAL_HOST': '/analytics',
        'USER': 'analytics_user',
        'PASSWORD': 'secret',
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    },
}
```

При вызове `AppConfig.ready()` Django-RMQ создаёт независимые `RabbitMQConnectionManager`, `ConsumersRegistry` и
`SetupRegistry` для каждого псевдонима. Эти объекты хранятся в модуле `django_rmq` под именами `connection_managers`,
`consumers_registries` и `setup_registries`.

---

## Параметр `using`

`Producer`, `Consumer`, `get_connection_manager`, `get_consumers_registry` и `get_setup_registry` принимают
необязательный именованный аргумент `using`:

```python
from django_rmq.producer import Producer
from django_rmq.consumer import Consumer
from django_rmq.queues.queue_config import QueueConfig

# Publishes to the 'analytics' broker.
analytics_producer: Producer = Producer(
    queue='page-views',
    using='analytics',
)

# Consumes from the 'default' broker.
order_consumer: Consumer = Consumer(
    queue=QueueConfig(name='orders'),
    using='default',
)
```

---

## Правила выбора псевдонима

Параметр `using` разрешается функцией `resolve_alias` в `django_rmq/utils.py`:

| Ситуация                                             | Результат                                 |
|------------------------------------------------------|-------------------------------------------|
| `using` не указан, настроен ровно один псевдоним     | Этот псевдоним используется автоматически |
| `using` не указан, настроено более одного псевдонима | Выбрасывается `ImproperlyConfigured`      |
| `using` указан и совпадает с псевдонимом             | Используется этот псевдоним               |
| `using` указан, но неизвестен                        | Выбрасывается `ImproperlyConfigured`      |
| `django_rmq` отсутствует в `INSTALLED_APPS`          | Выбрасывается `ImproperlyConfigured`      |

При наличии единственного псевдонима повсеместное опускание `using` безопасно и рекомендуется. После добавления второго
псевдонима каждый `Producer`, `Consumer` и аксессор реестра должен явно указывать `using`, чтобы избежать ошибки
неоднозначности.

---

## Регистрация консьюмеров и функций настройки по псевдониму

`get_consumers_registry` и `get_setup_registry` принимают `using`:

```python
# myapp/apps.py
from django.apps import AppConfig
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType

from django_rmq.consumer import Consumer
from django_rmq.queues.queue_config import QueueConfig
from django_rmq.registries.registry import get_consumers_registry
from django_rmq.registries.setup_registry import get_setup_registry


class MyAppConfig(AppConfig):
    name = 'myapp'

    def ready(self) -> None:
        from myapp.consumers import order_consumer, analytics_consumer

        get_consumers_registry(using='default').register(consumer=order_consumer)
        get_consumers_registry(using='analytics').register(consumer=analytics_consumer)

        def setup_analytics(channel: BlockingChannel) -> None:
            channel.exchange_declare(
                exchange='events',
                exchange_type=ExchangeType.topic,
                durable=True,
            )
            channel.queue_declare(queue='page-views', durable=True)
            channel.queue_bind(
                queue='page-views',
                exchange='events',
                routing_key='page.*',
            )

        get_setup_registry(using='analytics').register(fn=setup_analytics)
```

---

## Команды управления для конкретного псевдонима

Обе команды управления принимают `--using` для работы с одним псевдонимом. Без этого флага они выполняются для всех
настроенных псевдонимов.

```bash
# Declare topology for the 'analytics' alias only.
uv run python manage.py setup_rabbitmq_topology --using analytics

# Start consumers for the 'default' alias only.
uv run python manage.py start_consumers --using default

# Run for all aliases (omit --using).
uv run python manage.py setup_rabbitmq_topology
uv run python manage.py start_consumers
```

---

## Полный пример

В примере ниже настраиваются два независимых консьюмера на двух разных брокерах и проверяется, что их реестры являются
разными объектами:

```python
# tests/test_registries.py (adapted)
from django_rmq.registries.registry import get_consumers_registry
from django_rmq.registries.setup_registry import get_setup_registry

# After configuring two aliases:
default_consumers = get_consumers_registry(using='default')
analytics_consumers = get_consumers_registry(using='analytics')
default_setup = get_setup_registry(using='default')
analytics_setup = get_setup_registry(using='analytics')

assert default_consumers is not analytics_consumers
assert default_setup is not analytics_setup
```

Полный пример настройки с двумя псевдонимами (с подстановкой переменных окружения для продакшена):

```python
# settings.py
import os

RABBITMQ_CONNECTIONS: dict = {
    'default': {
        'HOST': os.environ.get('RMQ_DEFAULT_HOST', 'localhost'),
        'PORT': int(os.environ.get('RMQ_DEFAULT_PORT', '5672')),
        'VIRTUAL_HOST': os.environ.get('RMQ_DEFAULT_VHOST', '/'),
        'USER': os.environ.get('RMQ_DEFAULT_USER', 'guest'),
        'PASSWORD': os.environ.get('RMQ_DEFAULT_PASSWORD', 'guest'),
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    },
    'analytics': {
        'HOST': os.environ.get('RMQ_ANALYTICS_HOST', 'localhost'),
        'PORT': int(os.environ.get('RMQ_ANALYTICS_PORT', '5672')),
        'VIRTUAL_HOST': os.environ.get('RMQ_ANALYTICS_VHOST', '/analytics'),
        'USER': os.environ.get('RMQ_ANALYTICS_USER', 'guest'),
        'PASSWORD': os.environ.get('RMQ_ANALYTICS_PASSWORD', 'guest'),
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    },
}
```

Полный список обязательных ключей конфигурации см. в разделе [Конфигурация](/ru/1.0.5/configuration.html).
