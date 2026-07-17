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

`RABBITMQ_CONNECTIONS` — это `dict`, сопоставляющий имя алиаса с набором параметров соединения. Адресация узлов
задаётся либо скалярной парой `HOST`/`PORT` (один брокер), либо списком `NODES` (кластер); остальные ключи общие
для алиаса независимо от того, какая форма используется.

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

| Ключ                         | Тип          | Поле `RabbitMQConfig`                  | Описание                                                                                                                          |
|------------------------------|--------------|------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `HOST`                       | `str`        | `nodes` (одиночный `NodeConfig.host`)   | Имя хоста или IP-адрес брокера для одноузлового алиаса. Взаимоисключим с `NODES`.                                                |
| `PORT`                       | `int`        | `nodes` (одиночный `NodeConfig.port`)   | AMQP-порт брокера (как правило, `5672`) для одноузлового алиаса. Взаимоисключим с `NODES`.                                       |
| `NODES`                      | `list[dict]` | `nodes` (по одному `NodeConfig` на элемент) | Список узлов кластера; каждый элемент — `{'HOST': str, 'PORT': int}`. Взаимоисключим с `HOST`/`PORT`. См. [Кластеры](/ru/1.0.5/clusters.html). |
| `SHUFFLE_NODES`              | `bool`       | `shuffle_nodes`                          | Опционально; по умолчанию `False`. Перемешивает порядок узлов при каждой попытке подключения, чтобы распределить клиентов по кластеру. Имеет смысл только с `NODES`. |
| `VIRTUAL_HOST`               | `str`        | `virtual_host`                           | AMQP-виртуальный хост; общий для всех узлов алиаса.                                                                              |
| `USER`                       | `str`        | `user`                                    | Имя пользователя для аутентификации PlainCredentials; общее для всех узлов.                                                      |
| `PASSWORD`                   | `str`        | `password`                                | Пароль для аутентификации PlainCredentials; общий для всех узлов.                                                                |
| `HEARTBEAT`                  | `int`        | `heartbeat`                               | Интервал heartbeat в секундах; общий для всех узлов.                                                                             |
| `BLOCKED_CONNECTION_TIMEOUT` | `int`        | `blocked_connection_timeout`             | Количество секунд ожидания при блокировке соединения брокером; общее для всех узлов.                                             |
| `RECONNECT_INITIAL_BACKOFF`  | `float`      | `reconnect_initial_backoff`              | Начальная задержка переподключения потребителя в секундах.                                                                       |
| `RECONNECT_MAX_BACKOFF`      | `float`      | `reconnect_max_backoff`                  | Максимальная задержка переподключения потребителя (верхняя граница).                                                             |

`HOST`/`PORT` и `NODES` разрешаются в один и тот же кортеж `nodes` в `RabbitMQConfig` — скалярная форма является
лишь синтаксическим сахаром для одноэлементного кортежа `nodes`.

`RabbitMQConfig` — это `frozen dataclass`. После завершения `ready()` каждый алиас имеет свой неизменяемый экземпляр
конфигурации; изменение словаря настроек во время работы приложения не имеет никакого эффекта.

### Узлы кластера (NODES)

Чтобы указать для одного алиаса несколько узлов брокера, используйте `NODES` вместо `HOST`/`PORT`. `VIRTUAL_HOST`,
`USER`, `PASSWORD` и ключи таймаутов/backoff по-прежнему применяются ко всем узлам списка. `NODES` и `HOST`/`PORT`
взаимоисключающие — настраивайте либо одно, либо другое, но не оба сразу. См. [Кластеры](/ru/1.0.5/clusters.html) —
поведение при отказе узла и `SHUFFLE_NODES`.

```python
RABBITMQ_CONNECTIONS: dict[str, dict[str, object]] = {
    'default': {
        'NODES': [
            {'HOST': 'rmq-1.internal', 'PORT': 5672},
            {'HOST': 'rmq-2.internal', 'PORT': 5672},
            {'HOST': 'rmq-3.internal', 'PORT': 5672},
        ],
        'SHUFFLE_NODES': True,
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

Полный пример с несколькими алиасами см. в разделе [Несколько соединений](/ru/1.0.5/multiple-connections.html).

## Ошибки

| Ситуация                                      | Исключение             | Сообщение                                                                        |
|-----------------------------------------------|------------------------|----------------------------------------------------------------------------------|
| `RABBITMQ_CONNECTIONS` отсутствует или пуст   | `ImproperlyConfigured` | `django_rmq requires RABBITMQ_CONNECTIONS …`                                     |
| `'django_rmq'` не добавлен в `INSTALLED_APPS` | `ImproperlyConfigured` | `django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.`             |
| `using` не указан при нескольких алиасах      | `ImproperlyConfigured` | `Multiple RabbitMQ connections configured (…); pass using='<alias>' explicitly.` |
| `using` содержит неизвестный алиас            | `ImproperlyConfigured` | `Unknown RabbitMQ alias '<alias>'.`                                              |
| Указаны и `NODES`, и `HOST`/`PORT` для одного алиаса | `ImproperlyConfigured` | `RabbitMQ alias '<alias>': use either 'NODES' or 'HOST'/'PORT', not both.` |
| Не указаны ни `NODES`, ни `HOST`/`PORT`       | `ImproperlyConfigured` | `RabbitMQ alias '<alias>': define node addressing via 'NODES' or 'HOST'/'PORT'.` |
| `NODES` указан, но список пуст                | `ImproperlyConfigured` | `RabbitMQ alias '<alias>': 'NODES' must be a non-empty list.`                    |
| В элементе `NODES` не хватает `HOST` или `PORT` | `ImproperlyConfigured` | `RabbitMQ alias '<alias>': NODES[<index>] must define both 'HOST' and 'PORT'.`  |

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
