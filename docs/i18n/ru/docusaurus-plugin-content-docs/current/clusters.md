---
title: Кластеры
sidebar_position: 11
---

Один алиас соединения может указывать больше чем на один узел брокера. Django-RMQ
предоставляет **клиентский failover**: `pika` перебирает настроенные узлы по порядку, пока
один из них не примет соединение. При каждой попытке
подключения библиотека передаёт `pika` последовательность адресов узлов, и `pika` сама
проходит по этой последовательности.

Поддерживаются две топологии:

- **Список нод** — алиас перечисляет все ноды кластера через `NODES`, а `pika`
  сама выбирает, к какой из них подключиться.
- **Единая точка входа** перед кластером — балансировщик нагрузки или DNS-имя с несколькими
  A-записями — где алиас по-прежнему использует обычные `HOST`/`PORT`, а распределение и
  failover происходят на стороне сервера (то есть, например, балансировщика).

---

## Клиентский список узлов (NODES)

Настройте `NODES` — по одной записи на ноду кластера:

```python
# settings.py
RABBITMQ_CONNECTIONS: dict = {
    'default': {
        'NODES': [
            {'HOST': 'rmq-1.internal', 'PORT': 5672},
            {'HOST': 'rmq-2.internal', 'PORT': 5672},
            {'HOST': 'rmq-3.internal', 'PORT': 5672},
        ],
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

* `_resolve_nodes` в `django_rmq/apps.py` превращает каждую запись `{'HOST': ..., 'PORT': ...}`
  в `NodeConfig`;
* Остальные ключи (`VIRTUAL_HOST`, `USER`, `PASSWORD`, `HEARTBEAT`,
  `BLOCKED_CONNECTION_TIMEOUT`, `SOCKET_TIMEOUT`, `STACK_TIMEOUT`) применяются ко всем узлам списка.

Далее `RabbitMQConnectionManager.__init__` в `django_rmq/connections.py` строит по одному
`pika.ConnectionParameters` на каждый узел (`_make_node_parameters`), все они разделяют одни и те
же `PlainCredentials`, `virtual_host`, `heartbeat`, `blocked_connection_timeout`,
`socket_timeout` и `stack_timeout`, и передаёт весь список в `BlockingConnection`:

```python
# django_rmq/connections.py
setattr(self._local, attr, BlockingConnection(parameters=sequence))
```

`BlockingConnection` в pika принимает последовательность объектов `Parameters` и пробует законнектится
к каждому по очереди, пока один из них не подключится успешно — именно это и обеспечивает
failover по кластеру.

`NODES` взаимоисключающий со скалярной формой `HOST`/`PORT`. См. [Конфигурацию](./configuration.md)
для полного справочника параметров и случаев ошибок валидации, возникающих, если указаны
оба варианта или ни одного.

---

## Как работает failover при переподключении

Последовательность нод строится заново при каждой попытке подключения — не только при
первой. `RabbitMQConnectionManager._get_or_create_connection` вызывает
`_build_connection_sequence()` каждый раз, когда нужно открыть соединение, поэтому
переподключение получает свежую копию списка нод, а не переиспользует устаревшую.

Это напрямую связано с уже существующей [логикой переподключения](./reliability.md):
когда производитель сталкивается с reconnectable-ошибкой, он вызывает `reset_producer_channel()`
и переоткрывает соединение (повторяя публикацию один раз); потребитель переподключается с
экспоненциальным backoff. Поскольку переоткрытие соединения заново прогоняет
последовательность узлов, `pika` автоматически подключается к тому узлу, который сейчас
жив — никакого кластерно-осведомлённого кода в приложении не требуется.

Типичный сценарий failover, шаг за шагом:

- Нода `A` выходит из строя.
- Активное соединение с `A` обрывается.
- Происходит попытка (повтор продюсера или backoff-цикл потребителя) переоткрыть
  соединение.
- `pika` снова перебирает `[A, B, C]`: `A` отказывает в соединении, `B` же принимает его.
- Публикация/потребление возобновляются на ноде `B`.

Если `A` не отказывает в соединении, а молча отбрасывает пакеты (хост недоступен, разрыв
сети) или принимает TCP-соединение, но так и не завершает AMQP-handshake, `pika` потратит
на `A` до `SOCKET_TIMEOUT` / `STACK_TIMEOUT`, прежде чем перейти к `B`. См.
Таймауты узлов и время failover.

`get_producer_connection` и `get_consumer_connection` логируют debug-запись при каждом
открытии нового соединения, включая список узлов и флаг `shuffle`:

```python
# django_rmq/connections.py
logger.debug(
    {
        'source': source,
        'message': message,
        'data': {
            'nodes': [{'host': params.host, 'port': params.port} for params in sequence],
            'shuffle': self._shuffle_nodes,
        },
    }
)
```

---

## Распределение клиентов по кластеру (SHUFFLE_NODES)

`SHUFFLE_NODES` по умолчанию `False`: каждый клиент проходит список `NODES` в том порядке,
в котором он был объявлен, поэтому все клиенты выбирают ноду №1 первой. При большом
числе клиентских процессов это смещает нагрузку на эту ноду.

Установите `SHUFFLE_NODES: True`, чтобы перемешивать последовательность при каждой попытке
подключения:

```python
# django_rmq/connections.py — RabbitMQConnectionManager._build_connection_sequence
sequence: list[ConnectionParameters] = list(self._node_parameters)
if self._shuffle_nodes:
    random.shuffle(sequence)
return sequence
```

`shuffle_nodes` берётся из `RabbitMQConfig.shuffle_nodes`. Перемешивается только **копия**,
используемая для конкретной попытки подключения — настроенный в settings порядок `NODES`
никогда не изменяется, меняется лишь порядок перебора для этого конкретного соединения.

Включайте `SHUFFLE_NODES` для кластеров с большим числом клиентских процессов, чтобы
соединения распределялись по нодам, а не концентрировались на первой.

---

## Таймауты узлов и время failover

`pika` проходит последовательность нод **строго по очереди**: к следующей ноде она не
переходит, пока не зафейлилась попытка к текущей ноде.

| Что именно происходит с нодой                                             | Стоимость одной попытки                     |
|---------------------------------------------------------------------------|---------------------------------------------|
| Отклоняет соединение (порт закрыт, процесс остановлен, хост доступен)     | Быстро: ошибка сразу                        |
| Молча отбрасывает пакеты (хост выключен, `DROP` на файрволе, разрыв сети) | До `SOCKET_TIMEOUT` (по умолчанию `10.0` с) |
| Принимает TCP, но AMQP-handshake зависает                                 | До `STACK_TIMEOUT` (по умолчанию `15.0` с)  |

Худшая задержка до того, как `pika` дойдёт до живого узла, — это **сумма** по всем плохим
узлам, которые пробуются раньше. Для трёх узлов и значений по умолчанию (значения для
иллюстрации):

- первые два узла отбрасывают пакеты — около 20 с (2 × 10 с) до попытки к третьему;
- первые два узла зависают на handshake — около 30 с (2 × 15 с).

Эту цену приходится платить при каждом подключении и переподключении:

- первое соединение продюсера в потоке;
- переподключение после `reset_producer_channel()` — вызов `publish` блокируется на это время;
- каждое переподключение потребителя (поверх задержки backoff).

Логику переподключения см. в разделе [Надёжность](./reliability.md).

### Рекомендация

Уменьшите `SOCKET_TIMEOUT` и `STACK_TIMEOUT` у кластерного алиаса и сохраняйте
`STACK_TIMEOUT >= SOCKET_TIMEOUT`:

```python
# settings.py
RABBITMQ_CONNECTIONS: dict = {
    'default': {
        'NODES': [
            {'HOST': 'rmq-1.internal', 'PORT': 5672},
            {'HOST': 'rmq-2.internal', 'PORT': 5672},
            {'HOST': 'rmq-3.internal', 'PORT': 5672},
        ],
        # ... the remaining keys as above ...
        'SOCKET_TIMEOUT': 3.0,  # example values — tune for your network/TLS
        'STACK_TIMEOUT': 6.0,
    },
}
```

Не занижайте их слишком сильно: в медленной сети или при TLS здоровый узел может не
успеть ответить, и клиент его пропустит. Подробнее — в разделе
Таймауты подключения.

### Хелсчек

Команда `check_rabbitmq_connections` **не** обходит узлы по очереди. Она проверяет все
узлы параллельно со своими таймаутами из `RABBITMQ_HEALTHCHECK` и игнорирует `SOCKET_TIMEOUT` /
`STACK_TIMEOUT` алиаса и `SHUFFLE_NODES`. Алиас считается рабочим, как только отвечает
первый узел, поэтому мёртвый узел не задерживает вердикт. См.
[`check_rabbitmq_connections`](./management-commands.md#check_rabbitmq_connections) и
`RABBITMQ_HEALTHCHECK`.

---

## Альтернатива: балансировщик или DNS

Вместо перечисления всех узлов через `NODES` можно поставить перед кластером единый
адрес: load-balancer (например, `HAProxy`) или DNS-имя с несколькими
A-записями, указывающими на узлы кластера. В этом случае достаточно обычных `HOST`/`PORT` —
pika резолвит адрес и подключается к тому, который отвечает, а распределение и failover
происходят на стороне сервера (то есть балансировщика).

Trade-offs:

- **`NODES` (клиентская сторона)** — не требует дополнительной инфраструктуры; клиент знает
  обо всех нодах; логика failover находится в приложении (через `pika`).
- **Балансировщик / DNS (серверная сторона)** — единая точка входа для настройки;
  health-check'и централизованы на стороне LB/DNS; требуется разворачивать и поддерживать
  эту инфраструктуру; конфигурация клиента остаётся простой.

Эти два подхода не исключают друг друга на уровне протокола, но для конкретного алиаса
обычно выбирают один из них.

---

## Quorum-очереди

Кворумные очереди ортогональны адресации кластера — django_rmq объявляет их так же, как и
любой другой тип очереди, через поле `queue_type` на `QueueConfig`
(см. [`QueueType`](./api-reference.md#queuetype) в справочнике API):

```python
from django_rmq.queues.queue_config import QueueConfig,

QueueType

orders_queue: QueueConfig = QueueConfig(name='orders', queue_type=QueueType.QUORUM)
```

Объявление очереди с этим конфигом ставит `x-queue-type: quorum` при `queue_declare`.
Определите `orders_queue` в одном месте (например, в `myapp/queues.py`) и переиспользуйте
её в продюсере, потребителе и в любой setup-функции, которая ссылается на эту очередь —
см. [Топологию](./topology.md).

Либо объявляйте кворумную очередь из raw setup-функции, зарегистрированной через
setup-registry (см. [Реестры](./registries.md)) — это низкоуровневая альтернатива,
полезная, если очереди нужны аргументы, которых нет в `QueueConfig`:

```python
from pika.adapters.blocking_connection import BlockingChannel


def setup_quorum(channel: BlockingChannel) -> None:
    channel.queue_declare(
        queue='orders',
        durable=True,
        arguments={'x-queue-type': 'quorum'},
    )
```

Зарегистрируйте её так же, как и любую другую setup-функцию:

```python
from django_rmq.registries.setup_registry import get_setup_registry

get_setup_registry().register(fn=setup_quorum)
```

Publisher confirms уже включены на каждом канале продюсера (`confirm_delivery()` в
`django_rmq/connections.py` — см. [Надёжность](./reliability.md)), что хорошо сочетается
с кворумными очередями для обеспечения durability в рамках кластера :)

---

## См. также

- [Конфигурация](./configuration.md) — полный справочник параметров
  `NODES`/`SHUFFLE_NODES`/`SOCKET_TIMEOUT`/`STACK_TIMEOUT` и случаи ошибок валидации.
- [Management-команды](./management-commands.md) — `check_rabbitmq_connections` проверяет
  каждую ноду параллельно.
- [Надёжность](./reliability.md) — единичный повтор продюсера и переподключение
  потребителя с backoff.
- [Несколько подключений](./multiple-connections.md) — работа с несколькими алиасами.
- [Топология](./topology.md) — объявление exchanges, очередей и bindings через
  setup-функции.
- [Тестирование](./testing.md) — интеграционные тесты кластера, проверяющие это
  поведение failover на реальном кластере RabbitMQ с тремя нодами.
