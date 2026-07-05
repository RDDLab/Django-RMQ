---
title: Конфигурация
order: 3
---

# Конфигурация

## Регистрация приложения

Добавьте `'django_rmq'` в `INSTALLED_APPS` в настройках Django:

```python
INSTALLED_APPS: list[str] = [
    # ...
    'django_rmq',
]
```

При запуске Django `RabbitMQAppConfig.ready()` читает `RABBITMQ_CONNECTIONS` и для каждого алиаса создаёт
`RabbitMQConnectionManager`, `SetupRegistry` и `ConsumersRegistry`. Они сохраняются как атрибуты уровня модуля в
`django_rmq` и доступны с этого момента.

Если `RABBITMQ_CONNECTIONS` отсутствует или пуст на момент вызова `ready()`, Django выбросит `ImproperlyConfigured` и
откажется запускаться.

## `RABBITMQ_CONNECTIONS`

`RABBITMQ_CONNECTIONS` — это `dict`, сопоставляющий имя алиаса с набором параметров соединения. Все девять ключей
обязательны для каждого алиаса.

```python
RABBITMQ_CONNECTIONS: dict[str, dict[str, object]] = {
    'default': {
        'HOST': 'localhost',
        'PORT': 5672,
        'VIRTUAL_HOST': '/',
        'USER': 'guest',
        'PASSWORD': 'guest',
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    },
}
```

### Справочник параметров

| Ключ                         | Тип     | Поле `RabbitMQConfig`        | Описание                                                                                    |
|------------------------------|---------|------------------------------|---------------------------------------------------------------------------------------------|
| `HOST`                       | `str`   | `host`                       | Имя хоста или IP-адрес брокера.                                                             |
| `PORT`                       | `int`   | `port`                       | AMQP-порт брокера (как правило, `5672`).                                                    |
| `VIRTUAL_HOST`               | `str`   | `virtual_host`               | AMQP-виртуальный хост для подключения.                                                      |
| `USER`                       | `str`   | `user`                       | Имя пользователя для аутентификации PlainCredentials.                                       |
| `PASSWORD`                   | `str`   | `password`                   | Пароль для аутентификации PlainCredentials.                                                 |
| `HEARTBEAT`                  | `int`   | `heartbeat`                  | Интервал heartbeat в секундах, согласованный с брокером.                                    |
| `BLOCKED_CONNECTION_TIMEOUT` | `int`   | `blocked_connection_timeout` | Количество секунд ожидания при блокировке соединения брокером, прежде чем выбросить ошибку. |
| `RECONNECT_INITIAL_BACKOFF`  | `float` | `reconnect_initial_backoff`  | Начальная задержка переподключения потребителя в секундах.                                  |
| `RECONNECT_MAX_BACKOFF`      | `float` | `reconnect_max_backoff`      | Максимальная задержка переподключения потребителя (верхняя граница).                        |

`RabbitMQConfig` — это `frozen dataclass`. После завершения `ready()` каждый алиас имеет свой неизменяемый экземпляр
конфигурации; изменение словаря настроек во время работы приложения не имеет никакого эффекта.

## Одно соединение и несколько

Если определён ровно один алиас, параметр `using` можно не указывать в `Producer`, `Consumer` и командах управления —
единственный алиас разрешается автоматически.

Если определено два и более алиасов, `using='<alias>'` необходимо передавать явно. Если его не указать, будет выброшен
`ImproperlyConfigured` с сообщением, перечисляющим настроенные алиасы.

Один алиас:

```python
from django_rmq.producer import Producer

producer: Producer = Producer(queue='orders')
producer.publish(body='{"id": 1}')
```

Несколько алиасов — `using` обязателен:

```python
from django_rmq.producer import Producer

orders_producer: Producer = Producer(queue='orders', using='default')
analytics_producer: Producer = Producer(queue='events', using='analytics')
```

Полный пример с несколькими алиасами см. в разделе [Несколько соединений](/ru/multiple-connections.html).

## Ошибки

| Ситуация                                      | Исключение             | Сообщение                                                                        |
|-----------------------------------------------|------------------------|----------------------------------------------------------------------------------|
| `RABBITMQ_CONNECTIONS` отсутствует или пуст   | `ImproperlyConfigured` | `django_rmq requires RABBITMQ_CONNECTIONS …`                                     |
| `'django_rmq'` не добавлен в `INSTALLED_APPS` | `ImproperlyConfigured` | `django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.`             |
| `using` не указан при нескольких алиасах      | `ImproperlyConfigured` | `Multiple RabbitMQ connections configured (…); pass using='<alias>' explicitly.` |
| `using` содержит неизвестный алиас            | `ImproperlyConfigured` | `Unknown RabbitMQ alias '<alias>'.`                                              |

## Чтение данных для конфигурации подключения из переменных окружения

Хранить такие данные непосредственно в файлах настроек не рекомендуется для production-окружений. Распространённый
подход — читать их из переменных окружения:

```python
import os
from typing import Any

RABBITMQ_CONNECTIONS: dict[str, dict[str, Any]] = {
    'default': {
        'HOST': os.environ.get('RMQ_HOST', 'localhost'),
        'PORT': int(os.environ.get('RMQ_PORT', '5672')),
        'VIRTUAL_HOST': os.environ.get('RMQ_VIRTUAL_HOST', '/'),
        'USER': os.environ.get('RMQ_USER', 'guest'),
        'PASSWORD': os.environ.get('RMQ_PASSWORD', 'guest'),
        'HEARTBEAT': int(os.environ.get('RMQ_HEARTBEAT', '600')),
        'BLOCKED_CONNECTION_TIMEOUT': int(os.environ.get('RMQ_BLOCKED_CONNECTION_TIMEOUT', '300')),
        'RECONNECT_INITIAL_BACKOFF': float(os.environ.get('RMQ_RECONNECT_INITIAL_BACKOFF', '1.0')),
        'RECONNECT_MAX_BACKOFF': float(os.environ.get('RMQ_RECONNECT_MAX_BACKOFF', '30.0')),
    },
}
```

Вы также можете использовать `django-environ`, `python-decouple` или любую другую библиотеку для загрузки переменных
окружения — `RABBITMQ_CONNECTIONS` является обычным Python-словарём, поэтому подходит любой источник значений.
