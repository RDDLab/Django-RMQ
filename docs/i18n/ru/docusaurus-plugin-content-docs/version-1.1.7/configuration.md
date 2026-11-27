---
title: Конфигурация
sidebar_position: 3
---

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
`django_rmq` и доступны с этого момента. Также `ready()` разбирает необязательную настройку `RABBITMQ_HEALTHCHECK`
в `django_rmq.healthcheck_config` — см. `RABBITMQ_HEALTHCHECK`.

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
| `NODES`                      | `list[dict]` | `nodes` (по одному `NodeConfig` на элемент) | Список узлов кластера; каждый элемент — `{'HOST': str, 'PORT': int}`. Взаимоисключим с `HOST`/`PORT`. См. [Кластеры](./clusters.md). |
| `SHUFFLE_NODES`              | `bool`       | `shuffle_nodes`                          | Опционально; по умолчанию `False`. Перемешивает порядок узлов при каждой попытке подключения, чтобы распределить клиентов по кластеру. Имеет смысл только с `NODES`. |
| `VIRTUAL_HOST`               | `str`        | `virtual_host`                           | AMQP-виртуальный хост; общий для всех узлов алиаса.                                                                              |
| `USER`                       | `str`        | `user`                                    | Имя пользователя для аутентификации PlainCredentials; общее для всех узлов.                                                      |
| `PASSWORD`                   | `str`        | `password`                                | Пароль для аутентификации PlainCredentials; общий для всех узлов.                                                                |
| `HEARTBEAT`                  | `int`        | `heartbeat`                               | Интервал heartbeat в секундах; общий для всех узлов.                                                                             |
| `BLOCKED_CONNECTION_TIMEOUT` | `int`        | `blocked_connection_timeout`             | Количество секунд ожидания при блокировке соединения брокером; общее для всех узлов.                                             |
| `RECONNECT_INITIAL_BACKOFF`  | `float`      | `reconnect_initial_backoff`              | Начальная задержка переподключения потребителя в секундах.                                                                       |
| `RECONNECT_MAX_BACKOFF`      | `float`      | `reconnect_max_backoff`                  | Максимальная задержка переподключения потребителя (верхняя граница).                                                             |
| `SOCKET_TIMEOUT`             | `float`      | `socket_timeout`                         | Опционально; по умолчанию `10.0` (значение по умолчанию pika). Секунды ожидания TCP-соединения с одним узлом; допускается `int`. Общий для всех узлов. Каждый недоступный узел, который пробуется раньше живого, может добавить до этого значения к каждому (пере)подключению — см. Таймауты подключения. |
| `STACK_TIMEOUT`              | `float`      | `stack_timeout`                          | Опционально; по умолчанию `15.0` (значение по умолчанию pika). Секунды ожидания полного установления TCP + AMQP-соединения с одним узлом. Общий для всех узлов. |

`HOST`/`PORT` и `NODES` разрешаются в один и тот же кортеж `nodes` в `RabbitMQConfig` — скалярная форма является
лишь синтаксическим сахаром для одноэлементного кортежа `nodes`.

`RabbitMQConfig` — это `frozen dataclass`. После завершения `ready()` каждый алиас имеет свой неизменяемый экземпляр
конфигурации; изменение словаря настроек во время работы приложения не имеет никакого эффекта.

### Узлы кластера (NODES)

Чтобы указать для одного алиаса несколько узлов брокера, используйте `NODES` вместо `HOST`/`PORT`. `VIRTUAL_HOST`,
`USER`, `PASSWORD` и ключи таймаутов/backoff (включая `SOCKET_TIMEOUT` и `STACK_TIMEOUT`) по-прежнему применяются ко всем узлам списка. `NODES` и `HOST`/`PORT`
взаимоисключающие — настраивайте либо одно, либо другое, но не оба сразу. См. [Кластеры](./clusters.md) —
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

### Таймауты подключения (SOCKET_TIMEOUT, STACK_TIMEOUT)

Два необязательных ключа алиаса определяют, как долго pika ждёт при подключении к одному узлу:

- `SOCKET_TIMEOUT` — секунды ожидания TCP-соединения с одним узлом. По умолчанию `10.0`.
- `STACK_TIMEOUT` — секунды ожидания полного установления TCP + AMQP-соединения с одним узлом. По умолчанию `15.0`.

Значения по умолчанию совпадают со значениями pika, поэтому поведение не меняется, пока вы не зададите эти ключи. Оба
значения сохраняются в `RabbitMQConfig` (`socket_timeout`, `stack_timeout`) и передаются в `pika.ConnectionParameters`
для каждого узла методом `RabbitMQConnectionManager._make_node_parameters` (`django_rmq/connections.py`).

pika пробует узлы по очереди. Узел, который сразу отклоняет соединение, пропускается почти мгновенно, но узел, который
молча отбрасывает пакеты (хост недоступен, `DROP` на файрволе, сетевой разрыв), стоит до `SOCKET_TIMEOUT`, а узел,
который принимает TCP, но так и не завершает AMQP-рукопожатие, — до `STACK_TIMEOUT`. Эти задержки суммируются по всем
плохим узлам, которые пробуются раньше живого, при каждом подключении и переподключении. Подробнее — в разделе
Кластеры.

Оба значения должны быть положительными `int` или `float` (приводятся к `float`). Значения типа `bool` и строки
отклоняются с `ImproperlyConfigured` при запуске.

```python
RABBITMQ_CONNECTIONS: dict[str, dict[str, object]] = {
    'default': {
        'NODES': [
            {'HOST': 'rmq-1.internal', 'PORT': 5672},
            {'HOST': 'rmq-2.internal', 'PORT': 5672},
            {'HOST': 'rmq-3.internal', 'PORT': 5672},
        ],
        'SHUFFLE_NODES': True,
        'SOCKET_TIMEOUT': 3.0,  # example values — tune for your network/TLS
        'STACK_TIMEOUT': 6.0,
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

Слишком низкие значения приводят к ложным сбоям подключения в медленных сетях или при использовании TLS, поэтому
выбирайте значения с запасом относительно обычного времени подключения в вашем окружении.

Эти ключи не используются командой `check_rabbitmq_connections`; у хелсчека собственные таймауты — см.
`RABBITMQ_HEALTHCHECK`.

## `RABBITMQ_HEALTHCHECK`

`RABBITMQ_HEALTHCHECK` — необязательная глобальная настройка (не на уровне алиаса), которую использует только команда
управления `check_rabbitmq_connections`. Это `dict` с тремя необязательными ключами; пустой `{}` означает все значения
по умолчанию.

| Ключ             | Тип     | По умолчанию | Поле `HealthcheckConfig` | Описание                                                                                                                                                                  |
|------------------|---------|--------------|--------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `DEADLINE`       | `float` | `15.0`       | `deadline`               | Общий бюджет времени в секундах на всю проверку (все алиасы). По его истечении алиасы, по которым ещё нет решения, завершаются ошибкой `TimeoutError`. `--timeout` переопределяет его для одного запуска. |
| `SOCKET_TIMEOUT` | `float` | `5.0`        | `socket_timeout`         | Секунды ожидания TCP-соединения с одним узлом во время проверки.                                                                                                          |
| `STACK_TIMEOUT`  | `float` | `10.0`       | `stack_timeout`          | Секунды ожидания полного установления TCP + AMQP-соединения с одним узлом во время проверки.                                                                              |

Проверка игнорирует `SOCKET_TIMEOUT`/`STACK_TIMEOUT` алиаса и `SHUFFLE_NODES`, поэтому её длительность не зависит от
порядка узлов.

```python
RABBITMQ_HEALTHCHECK: dict[str, float] = {
    'DEADLINE': 15.0,
    'SOCKET_TIMEOUT': 5.0,
    'STACK_TIMEOUT': 10.0,
}
```

Это значения по умолчанию; чтобы их использовать, просто не задавайте настройку.

Валидация выполняется в `RabbitMQAppConfig.ready()`, который вызывается в каждом процессе Django. Поэтому неверная
настройка приводит к ошибке при запуске воркера, хотя сама команда хелсчека пропускает системные проверки (проба,
запущенная с неверной настройкой, падает с traceback). `ImproperlyConfigured` выбрасывается, если:

- настройка не является `dict`;
- есть неизвестный ключ (допустимы: `DEADLINE`, `SOCKET_TIMEOUT`, `STACK_TIMEOUT`);
- значение не является положительным числом секунд (`bool` и строки отклоняются).

Перекрёстной проверки ключей нет. Держите таймауты узла не больше `DEADLINE`; иначе зависший узел будет показан как
`no answer`, а не со своей собственной ошибкой. О том, как эти значения соотносятся с таймаутом пробы контейнера, см.
Бюджет времени хелсчека.

Разобранное значение доступно как `django_rmq.healthcheck_config` (`HealthcheckConfig` или `None` до вызова `ready()`);
см. `HealthcheckConfig`.

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

Полный пример с несколькими алиасами см. в разделе [Несколько соединений](./multiple-connections.md).

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
| `SOCKET_TIMEOUT` / `STACK_TIMEOUT` не является положительным числом (`0`, отрицательное, `bool`, строка) | `ImproperlyConfigured` | `RabbitMQ alias '<alias>': 'SOCKET_TIMEOUT' must be a positive number of seconds, got <repr>.` (аналогично для `'STACK_TIMEOUT'`) |
| `RABBITMQ_HEALTHCHECK` не является `dict` | `ImproperlyConfigured` | `` `RABBITMQ_HEALTHCHECK` must be a dict. `` |
| В `RABBITMQ_HEALTHCHECK` есть неизвестный ключ | `ImproperlyConfigured` | `` `RABBITMQ_HEALTHCHECK`: unknown key(s) <KEYS>; allowed: DEADLINE, SOCKET_TIMEOUT, STACK_TIMEOUT. `` |
| Значение в `RABBITMQ_HEALTHCHECK` не является положительным числом | `ImproperlyConfigured` | `` `RABBITMQ_HEALTHCHECK`: 'DEADLINE' must be a positive number of seconds, got <repr>. `` (аналогично для остальных ключей) |

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
        'SOCKET_TIMEOUT': float(os.environ.get('RMQ_SOCKET_TIMEOUT', '10.0')),
        'STACK_TIMEOUT': float(os.environ.get('RMQ_STACK_TIMEOUT', '15.0')),
    },
}
```

Вы также можете использовать `django-environ`, `python-decouple` или любую другую библиотеку для загрузки переменных
окружения — `RABBITMQ_CONNECTIONS` является обычным Python-словарём, поэтому подходит любой источник значений.
