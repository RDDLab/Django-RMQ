---
title: Справочник API
sidebar_position: 13
---

Плоский справочник по всем публичным символам в `django_rmq`. Сигнатуры и описания параметров взяты непосредственно из
исходного кода.

---

## Producer

```python
from django_rmq.producer import Producer
```

Публикует сообщения в RabbitMQ через потоко-локальный блокирующий канал.

### `Producer.__init__`

```python
def __init__(
    self,
    exchange: str = '',
    queue: QueueConfig | str = '',
    using: str | None = None,
) -> None
```

| Параметр   | Тип                  | По умолчанию | Описание                                                                                                                                                                                         |
|------------|----------------------|--------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `exchange` | `str`                | `''`         | Имя обменника. Пустая строка означает обменник по умолчанию (direct).                                                                                                                            |
| `queue`    | `QueueConfig \| str` | `''`         | Конфигурация очереди или её имя. Используется как ключ маршрутизации по умолчанию; объявляется лениво при первой публикации. Пустая строка отключает объявление очереди (режим только-обменник). |
| `using`    | `str \| None`        | `None`       | Псевдоним соединения из `RABBITMQ_CONNECTIONS`. Можно не указывать, если настроен ровно один псевдоним.                                                                                          |

### `Producer.publish`

```python
def publish(
    self,
    body: str | bytes,
    routing_key: str | None = None,
    properties: BasicProperties | None = None,
) -> None
```

| Параметр      | Тип                       | По умолчанию | Описание                                                                                                                                                             |
|---------------|---------------------------|--------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `body`        | `str \| bytes`            | обязательный | Тело сообщения. Строки кодируются в байты (UTF-8).                                                                                                                   |
| `routing_key` | `str \| None`             | `None`       | Ключ маршрутизации. По умолчанию используется `self.queue` (имя очереди), если не указан.                                                                            |
| `properties`  | `BasicProperties \| None` | `None`       | Свойства AMQP-сообщения. Если не указаны, создаются с `content_type='application/json'`. `delivery_mode` всегда принудительно устанавливается в `2` (`persistence`). |

**Returns:** `None`

**Raises:**

- `pika.exceptions.UnroutableError` — брокер вернул сообщение, так как ни одна очередь не совпала с ключом
  маршрутизации (требуются подтверждения публикации + `mandatory=True`, оба всегда включены).
- `pika.exceptions.NackError` — брокер отклонил (nack) сообщение.
- Любое исключение из `_RECONNECTABLE_ERRORS`, если и первая попытка, и единственный повтор завершились ошибкой.

### `Producer.__call__`

Позволяет использовать экземпляр `Producer` как декоратор функции. Декорируемая функция должна возвращать `str`, `bytes`
или `None`. Возвращаемое значение публикуется автоматически; `None` пропускает публикацию.

```python
def __call__(
    self,
    func: Callable[..., str | bytes | None],
) -> Callable[..., str | bytes | None]
```

**Raises:** `TypeError`, если декорируемая функция возвращает тип, отличный от `str`, `bytes` или `None`.

**Пример:**

```python
from django_rmq.producer import Producer

producer: Producer = Producer(queue='notifications')


@producer
def build_notification(user_id: int) -> str:
    return f'{{"user_id": {user_id}}}'
```

---

## Consumer

```python
from django_rmq.consumer import Consumer
```

Потребляет сообщения из одной очереди RabbitMQ с одним зарегистрированным обработчиком. При транзитных ошибках AMQP
переподключается с экспоненциальной задержкой.

### `Consumer.__init__`

```python
def __init__(
    self,
    queue: QueueConfig | str,
    prefetch_count: int = 1,
    reconnect_initial_backoff: float | None = None,
    reconnect_max_backoff: float | None = None,
    using: str | None = None,
) -> None
```

| Параметр                    | Тип                  | По умолчанию | Описание                                                                                                                                        |
|-----------------------------|----------------------|--------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| `queue`                     | `QueueConfig \| str` | обязательный | Очередь для потребления. `QueueConfig` инициирует активное объявление с аргументами; обычная строка инициирует durable-объявление.              |
| `prefetch_count`            | `int`                | `1`          | Максимальное количество неподтверждённых сообщений, доставляемых одновременно (`basic_qos`).                                                    |
| `reconnect_initial_backoff` | `float \| None`      | `None`       | Начальная задержка перед переподключением в секундах. При `None` берётся из конфигурации псевдонима.                                            |
| `reconnect_max_backoff`     | `float \| None`      | `None`       | Максимальная задержка перед переподключением в секундах (ограничение экспоненциальной задержки). При `None` берётся из конфигурации псевдонима. |
| `using`                     | `str \| None`        | `None`       | Псевдоним соединения. Можно не указывать, если настроен ровно один псевдоним.                                                                   |

### `Consumer.handler`

```python
def handler(self, func: MessageCallback) -> MessageCallback
```

Регистрирует коллбэк для входящих сообщений. Может использоваться как декоратор.

**Raises:** `RuntimeError`, если на этом консьюмере уже зарегистрирован обработчик.

### `Consumer.__call__`

Сокращение для `@consumer.handler`. Идентичное поведение.

```python
def __call__(self, func: MessageCallback) -> MessageCallback
```

### `Consumer.consume`

```python
def consume(self, stop_event: threading.Event | None = None) -> None
```

Запускает цикл потребления. При транзитных ошибках переподключается. Завершается при установке `stop_event` или при
возникновении неустранимой ошибки.

| Параметр     | Тип                       | По умолчанию | Описание                                                                                                                                        |
|--------------|---------------------------|--------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| `stop_event` | `threading.Event \| None` | `None`       | Событие для сигнала о плановом завершении. При `None` создаётся внутреннее событие (никогда не устанавливается) — консьюмер работает до ошибки. |

### Свойства `Consumer`

| Свойство         | Тип           | Описание                                                                                             |
|------------------|---------------|------------------------------------------------------------------------------------------------------|
| `prefetch_count` | `int`         | Максимальное количество неподтверждённых сообщений, доставляемых одновременно.                       |
| `using`          | `str \| None` | Псевдоним соединения или `None`, если единственный псевдоним используется неявно.                    |
| `handler_name`   | `str`         | Имя зарегистрированной функции-обработчика или `'unregistered'`, если обработчик не зарегистрирован. |

---

## MessageCallback

```python
from django_rmq.consumer import MessageCallback
```

Псевдоним типа для сигнатуры вызываемого обработчика:

```python
MessageCallback = Callable[
    [BlockingChannel, Basic.Deliver, BasicProperties, bytes],
    None,
]
```

| Аргумент | Тип               | Описание                                                                                     |
|----------|-------------------|----------------------------------------------------------------------------------------------|
| `ch`     | `BlockingChannel` | Канал, по которому доставлено сообщение. Используется для вызова `basic_ack` / `basic_nack`. |
| `method` | `Basic.Deliver`   | Метаданные доставки, включая `delivery_tag`.                                                 |
| `props`  | `BasicProperties` | Свойства AMQP-сообщения.                                                                     |
| `body`   | `bytes`           | Необработанное тело сообщения.                                                               |

---

## QueueConfig

```python
from django_rmq.queues.queue_config import QueueConfig,

QueueType
```

`frozen dataclass` для декларативной конфигурации очереди.

```python
@dataclass(frozen=True)
class QueueConfig:
    name: str
    durable: bool = True
    queue_type: QueueType | None = None
    dead_letter_exchange: str | None = None
    dead_letter_routing_key: str | None = None
```

| Поле                      | Тип                 | По умолчанию | Описание                                                                                           |
|---------------------------|---------------------|--------------|----------------------------------------------------------------------------------------------------|
| `name`                    | `str`               | обязательное | Имя очереди. Также используется как `str(queue_config)`.                                           |
| `durable`                 | `bool`              | `True`       | Очередь переживает перезапуск брокера.                                                             |
| `queue_type`              | `QueueType \| None` | `None`       | Устанавливает `x-queue-type` при объявлении; при `None` используется `default_queue_type` брокера. |
| `dead_letter_exchange`    | `str \| None`       | `None`       | Обменник, куда маршрутизируются dead-letter сообщения (`x-dead-letter-exchange`).                  |
| `dead_letter_routing_key` | `str \| None`       | `None`       | Ключ маршрутизации для dead-letter сообщений (`x-dead-letter-routing-key`).                        |

### `QueueType`

Enum поддерживаемых типов очередей RabbitMQ; значение члена сериализуется брокеру как аргумент `x-queue-type`.

| Член      | Значение    |
|-----------|-------------|
| `CLASSIC` | `'classic'` |
| `QUORUM`  | `'quorum'`  |
| `STREAM`  | `'stream'`  |

`QueueType` наследуется от `str` (а не от `StrEnum`, доступного только в 3.11+, чтобы сохранить совместимость с Python
3.10), поэтому каждый член — обычная строка и сериализуется брокеру как есть. Если `queue_type` не задан на
`QueueConfig`, брокер применяет свой `default_queue_type`.

### Свойство `QueueConfig.arguments`

```python
@property
def arguments(self) -> dict[str, Any] | None
```

Строит словарь AMQP `arguments` для объявления очереди на основе `queue_type` (`x-queue-type`) и полей dead-letter.
Возвращает `None`, если ничего из этого не задано.

---

## RabbitMQConfig

```python
from django_rmq.dto.rabbitmq_config import RabbitMQConfig
```

`frozen dataclass` с разрешённой конфигурацией для одного псевдонима соединения. Создаётся внутри
`RabbitMQAppConfig.ready()` из настройки `RABBITMQ_CONNECTIONS`. Доступен через `RabbitMQConnectionManager.config`.

```python
@dataclass(frozen=True)
class RabbitMQConfig:
    nodes: tuple[NodeConfig, ...]
    virtual_host: str
    user: str
    password: str
    heartbeat: int
    blocked_connection_timeout: int
    reconnect_initial_backoff: float
    reconnect_max_backoff: float
    shuffle_nodes: bool = False
    socket_timeout: float = 10.0
    stack_timeout: float = 15.0
```

Псевдоним может указывать на одну ноду или на несколько (кластер). Все ноды используют один и тот же
виртуальный хост и учётные данные; различаются только хост и порт.

| Поле                         | Тип                      | По умолчанию | Описание                                                                                                                                                       |
|------------------------------|--------------------------|--------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `nodes`                      | `tuple[NodeConfig, ...]` | обязательное | Один или несколько адресов узлов. pika пробует их по порядку, пока один из них не примет соединение.                                                           |
| `virtual_host`               | `str`                    | обязательное | AMQP-виртуальный хост для подключения.                                                                                                                         |
| `user`                       | `str`                    | обязательное | Имя пользователя для `PlainCredentials`.                                                                                                                       |
| `password`                   | `str`                    | обязательное | Пароль для `PlainCredentials`.                                                                                                                                 |
| `heartbeat`                  | `int`                    | обязательное | Интервал heartbeat в секундах.                                                                                                                                 |
| `blocked_connection_timeout` | `int`                    | обязательное | Секунды ожидания, пока брокер блокирует соединение, прежде чем оно завершится ошибкой.                                                                         |
| `reconnect_initial_backoff`  | `float`                  | обязательное | Начальная задержка переподключения консьюмера в секундах.                                                                                                      |
| `reconnect_max_backoff`      | `float`                  | обязательное | Максимальная задержка переподключения консьюмера в секундах (ограничение экспоненциальной задержки).                                                           |
| `shuffle_nodes`              | `bool`                   | `False`      | Перемешивать порядок нод при каждой попытке подключения.                                                                                                       |
| `socket_timeout`             | `float`                  | `10.0`       | Секунды ожидания TCP-соединения с одним узлом (`socket_timeout` в pika). Каждый недоступный узел, опрошенный до живого, добавляет к попытке до этого значения. |
| `stack_timeout`              | `float`                  | `15.0`       | Секунды ожидания полного цикла TCP + AMQP одного узла (`stack_timeout` в pika).                                                                                |

### `NodeConfig`

```python
from django_rmq.dto.rabbitmq_config import NodeConfig
```

```python
@dataclass(frozen=True)
class NodeConfig:
    host: str
    port: int
```

Неизменяемый адрес одного узла RabbitMQ в рамках псевдонима соединения.

| Поле   | Тип   | Описание              |
|--------|-------|-----------------------|
| `host` | `str` | Хостнейм или IP узла. |
| `port` | `int` | AMQP-порт узла.       |

---

## HealthcheckConfig

```python
from django_rmq.dto.healthcheck_config import HealthcheckConfig
```

```python
@dataclass(frozen=True)
class HealthcheckConfig:
    deadline: float = 15.0
    socket_timeout: float = 5.0
    stack_timeout: float = 10.0
```

| Поле             | Тип     | По умолчанию | Ключ настройки   | Описание                                                                                                              |
|------------------|---------|--------------|------------------|-----------------------------------------------------------------------------------------------------------------------|
| `deadline`       | `float` | `15.0`       | `DEADLINE`       | Общий дедлайн в секундах на проверку всех псевдонимов. По истечении псевдонимы без живого узла считаются неуспешными. |
| `socket_timeout` | `float` | `5.0`        | `SOCKET_TIMEOUT` | Секунды ожидания TCP-соединения с одним узлом.                                                                        |
| `stack_timeout`  | `float` | `10.0`       | `STACK_TIMEOUT`  | Секунды ожидания полного подъёма TCP + AMQP одного узла.                                                              |

---

## RabbitMQConnectionManager

```python
from django_rmq.connections import RabbitMQConnectionManager
```

Управляет потоко-локальными соединениями для ролей продюсера и консьюмера. Создаётся по одному экземпляру на псевдоним в
`RabbitMQAppConfig.ready()`.

### `RabbitMQConnectionManager.__init__`

```python
def __init__(self, config: RabbitMQConfig) -> None
```

Строит по одному `ConnectionParameters` на узел, каждый с `socket_timeout` и `stack_timeout` псевдонима.

### `RabbitMQConnectionManager.get_producer_connection`

```python
def get_producer_connection(self) -> BlockingConnection
```

Возвращает потоко-локальное `BlockingConnection`, используемое продюсерами в текущем потоке. Создаётся при первом
обращении; повторно использует кешированный экземпляр, пока соединение открыто.

### `RabbitMQConnectionManager.get_consumer_connection`

```python
def get_consumer_connection(self) -> BlockingConnection
```

Возвращает потоко-локальное `BlockingConnection`, используемое консьюмерами в текущем потоке. Хранится отдельно от
соединения продюсера, чтобы публикация из обработчика была безопасной.

### `RabbitMQConnectionManager.get_producer_channel`

```python
def get_producer_channel(self) -> BlockingChannel
```

Возвращает потоко-локальный канал продюсера с включёнными подтверждениями публикации (`confirm_delivery()`). Создаётся
при первом обращении; повторно используется, пока открыт.

### `RabbitMQConnectionManager.reset_producer_channel`

```python
def reset_producer_channel(self) -> None
```

Закрывает и удаляет кешированный канал продюсера и соединение. Вызывается автоматически `Producer.publish` после
восстанавливаемой ошибки, чтобы следующая публикация открыла новый канал. Безопасен к вызову даже при отсутствии
кешированного канала.

### `RabbitMQConnectionManager.build_probe_parameters`

```python
def build_probe_parameters(
    self,
    socket_timeout: float,
    stack_timeout: float,
) -> list[ConnectionParameters]
```

| Параметр         | Тип     | По умолчанию | Описание                                        |
|------------------|---------|--------------|-------------------------------------------------|
| `socket_timeout` | `float` | обязательный | Секунды ожидания TCP-соединения с узлом.        |
| `stack_timeout`  | `float` | обязательный | Секунды ожидания полного цикла TCP + AMQP узла. |

**Returns:** `list[ConnectionParameters]` — по одному элементу на узел, в порядке `NODES`.

Строит независимые параметры коннекшена для каждого узла, чтобы проверять узлы по отдельности. Порядок соответствует
`NODES` и никогда не перемешивается; при каждом вызове строится новый список, ничего не кешируется. Соединения не
открываются. Учётные данные, виртуальный хост, heartbeat и таймаут блокировки соединения те же, что у псевдонима;
`socket_timeout` / `stack_timeout` и `shuffle_nodes` псевдонима игнорируются. Используется командой
`check_rabbitmq_connections`.

---

## get_connection_manager

```python
from django_rmq.connections import get_connection_manager
```

```python
def get_connection_manager(using: str | None = None) -> RabbitMQConnectionManager
```

Возвращает `RabbitMQConnectionManager` для указанного псевдонима.

| Параметр | Тип           | По умолчанию | Описание                                                                          |
|----------|---------------|--------------|-----------------------------------------------------------------------------------|
| `using`  | `str \| None` | `None`       | Псевдоним для разрешения. Можно не указывать, если настроен ровно один псевдоним. |

**Raises:** `ImproperlyConfigured` — псевдоним не найден, неоднозначность (несколько псевдонимов, `using` не указан) или
`django_rmq` не инициализирован.

---

## ConsumersRegistry

```python
from django_rmq.registries.registry import ConsumersRegistry
```

Содержит консьюмеры, зарегистрированные для одного псевдонима соединения.

### `ConsumersRegistry.register`

```python
def register(self, consumer: Consumer) -> None
```

Добавляет консьюмер в реестр.

### `ConsumersRegistry.all`

```python
def all(self) -> list[Consumer]
```

Возвращает копию всех зарегистрированных консьюмеров. Изменение возвращённого списка не влияет на реестр.

---

## get_consumers_registry

```python
from django_rmq.registries.registry import get_consumers_registry
```

```python
def get_consumers_registry(using: str | None = None) -> ConsumersRegistry
```

Возвращает `ConsumersRegistry` для указанного псевдонима.

**Raises:** `ImproperlyConfigured` — те же условия, что и в `get_connection_manager`.

---

## SetupRegistry

```python
from django_rmq.registries.setup_registry import SetupRegistry
```

Содержит идемпотентные функции настройки топологии для одного псевдонима соединения.

### `SetupRegistry.register`

```python
def register(self, fn: SetupFn) -> None
```

Добавляет функцию настройки в реестр. Функции вызываются в порядке регистрации.

### `SetupRegistry.run_all`

```python
def run_all(self, channel: BlockingChannel) -> None
```

Выполняет все зарегистрированные функции настройки на указанном канале в порядке регистрации.

---

## get_setup_registry

```python
from django_rmq.registries.setup_registry import get_setup_registry
```

```python
def get_setup_registry(using: str | None = None) -> SetupRegistry
```

Возвращает `SetupRegistry` для указанного псевдонима.

**Raises:** `ImproperlyConfigured` — те же условия, что и в `get_connection_manager`.

---

## SetupFn

```python
from django_rmq.registries.setup_registry import SetupFn
```

Псевдоним типа для вызываемого объекта настройки топологии:

```python
SetupFn = Callable[[BlockingChannel], None]
```

`SetupFn` получает открытый `BlockingChannel` и должна быть идемпотентной (безопасной для многократного вызова с
одинаковым результатом).

---

## RabbitMQAppConfig

```python
from django_rmq.apps import RabbitMQAppConfig
```

Django `AppConfig` для `django_rmq`. Регистрируется автоматически при наличии `'django_rmq'` в `INSTALLED_APPS`.

### `RabbitMQAppConfig.ready`

```python
def ready(self) -> None
```

Читает `RABBITMQ_CONNECTIONS` из настроек Django и создаёт для каждого псевдонима один `RabbitMQConnectionManager`, один
`SetupRegistry` и один `ConsumersRegistry`. Сохраняет их в модуле `django_rmq` под именами `connection_managers`,
`setup_registries` и `consumers_registries`. Также разбирает необязательную настройку `RABBITMQ_HEALTHCHECK` в
`django_rmq.healthcheck_config`, поэтому её ошибки проявляются при старте воркера, а не в хелсчек-пробе.

**Raises:** `ImproperlyConfigured` — `RABBITMQ_CONNECTIONS` отсутствует или пуст, адресация узлов отсутствует или
некорректна, `SOCKET_TIMEOUT` / `STACK_TIMEOUT` не является положительным числом либо `RABBITMQ_HEALTHCHECK`
некорректна. См. [Error cases](./configuration.md) в руководстве по конфигурации.

---

## Глобальные переменные модуля (`django_rmq`)

```python
import django_rmq

django_rmq.connection_managers  # dict[str, RabbitMQConnectionManager] | None
django_rmq.setup_registries  # dict[str, SetupRegistry] | None
django_rmq.consumers_registries  # dict[str, ConsumersRegistry] | None
django_rmq.healthcheck_config  # HealthcheckConfig | None
```

Все четыре имеют значение `None` до выполнения `RabbitMQAppConfig.ready()`. Используйте функции-аксессоры (
`get_connection_manager`, `get_consumers_registry`, `get_setup_registry`) вместо прямого обращения к первым трём
словарям.

---

## Команды управления

### `setup_rabbitmq_topology`

```bash
uv run python manage.py setup_rabbitmq_topology [--using ALIAS]
```

Объявляет все обменники, очереди и привязки, зарегистрированные в `SetupRegistry`, для одного или всех псевдонимов.
Идемпотентна — безопасна для запуска при каждом деплое.

| Опция           | Описание                                                                                     |
|-----------------|----------------------------------------------------------------------------------------------|
| `--using ALIAS` | Выполнить только для указанного псевдонима. Без этой опции выполняется для всех псевдонимов. |

После настройки выводит отчёт об объявленных обменниках, очередях и привязках, дедуплицированных по имени.

### `check_rabbitmq_connections`

```bash
uv run python manage.py check_rabbitmq_connections [--using ALIAS] [--format {json,text}] [--timeout SECONDS] [--skip-checks]
```

Хелсчек для контейнеров. Параллельно проверяет каждый узел одного или всех alias'ов (открывает соединение и
сразу закрывает его) с таймаутами из `RABBITMQ_HEALTHCHECK`. Алиас считается здоровым, как только отвечает один из
его узлов; псевдонимы без живого узла получают FAIL, когда отказали все узлы или истёк дедлайн. Завершается с кодом `0`,
если все псевдонимы здоровы, и `1` в противном случае.

| Опция                  | Описание                                                                                                    |
|------------------------|-------------------------------------------------------------------------------------------------------------|
| `--using ALIAS`        | Проверить только указанный алиас. Без этой опции проверяются все.                                           |
| `--format {json,text}` | Формат вывода: `text` (по умолчанию, `key=value`) или `json` (один объект на строку).                       |
| `--timeout SECONDS`    | Общий дедлайн в секундах. Должен быть больше `0`. По умолчанию `RABBITMQ_HEALTHCHECK['DEADLINE']` (`15.0`). |
| `--skip-checks`        | Ничего не делает, оставлена для обратной совместимости: команда никогда не запускает системные проверки.    |

Выходные события, коды возврата и примеры см. в разделе [Команды управления](./management-commands.md).

### `start_consumers`

```bash
uv run python manage.py start_consumers [--using ALIAS]
```

Запускает все консьюмеры, зарегистрированные в `ConsumersRegistry`, для одного или всех псевдонимов. Каждый консьюмер
работает в отдельном потоке, разделяя единый `stop_event`. `SIGTERM` и `SIGINT` устанавливают это событие для планового
завершения; команда ожидает завершения всех потоков перед возвратом.

| Опция           | Описание                                                                                      |
|-----------------|-----------------------------------------------------------------------------------------------|
| `--using ALIAS` | Запустить консьюмеры только для указанного псевдонима. Без этой опции — для всех псевдонимов. |

---

## Справочник настроек

Ключи каждого псевдонима в `RABBITMQ_CONNECTIONS`:

| Ключ                         | Тип                    | Обязательный                  | Описание                                                                                                   |
|------------------------------|------------------------|-------------------------------|------------------------------------------------------------------------------------------------------------|
| `HOST`                       | `str`                  | вместе с `PORT`, либо `NODES` | Хостнейм или IP брокера. Взаимоисключающий с `NODES`.                                                      |
| `PORT`                       | `int`                  | вместе с `HOST`, либо `NODES` | AMQP-порт (обычно `5672`). Взаимоисключающий с `NODES`.                                                    |
| `NODES`                      | `list[dict[str, Any]]` | либо `HOST` / `PORT`          | Непустой список узлов, у каждого есть `HOST` и `PORT`. Взаимоисключающий с `HOST` / `PORT`.                |
| `VIRTUAL_HOST`               | `str`                  | да                            | Виртуальный хост (например, `'/'`).                                                                        |
| `USER`                       | `str`                  | да                            | Имя пользователя для аутентификации.                                                                       |
| `PASSWORD`                   | `str`                  | да                            | Пароль для аутентификации.                                                                                 |
| `HEARTBEAT`                  | `int`                  | да                            | Интервал heartbeat в секундах.                                                                             |
| `BLOCKED_CONNECTION_TIMEOUT` | `int`                  | да                            | Секунды до таймаута заблокированного соединения.                                                           |
| `RECONNECT_INITIAL_BACKOFF`  | `float`                | да                            | Начальная задержка переподключения консьюмера в секундах.                                                  |
| `RECONNECT_MAX_BACKOFF`      | `float`                | да                            | Максимальная задержка переподключения консьюмера (ограничение задержки).                                   |
| `SHUFFLE_NODES`              | `bool`                 | нет (по умолчанию `False`)    | Перемешивать порядок узлов при каждой попытке подключения.                                                 |
| `SOCKET_TIMEOUT`             | `float`                | нет (по умолчанию `10.0`)     | Секунды ожидания TCP-соединения с одним узлом. Положительное число; `bool` и строки отклоняются.           |
| `STACK_TIMEOUT`              | `float`                | нет (по умолчанию `15.0`)     | Секунды ожидания полного подъёма TCP + AMQP одного узла. Положительное число; `bool` и строки отклоняются. |

Обязательные ключи: `VIRTUAL_HOST`, `USER`, `PASSWORD`, `HEARTBEAT`, `BLOCKED_CONNECTION_TIMEOUT`,
`RECONNECT_INITIAL_BACKOFF`, `RECONNECT_MAX_BACKOFF`. Отсутствующий ключ вызывает `KeyError` в процессе
`AppConfig.ready()`. Адресация узлов тоже обязательна: либо `HOST` и `PORT`, либо `NODES` (но не оба сразу); иначе
выбрасывается `ImproperlyConfigured`. `SHUFFLE_NODES`, `SOCKET_TIMEOUT` и `STACK_TIMEOUT` необязательны.

Необязательная глобальная настройка `RABBITMQ_HEALTHCHECK` — словарь; каждый ключ необязателен, `{}` оставляет все
значения по умолчанию:

| Ключ             | Тип     | По умолчанию | Описание                                                         |
|------------------|---------|--------------|------------------------------------------------------------------|
| `DEADLINE`       | `float` | `15.0`       | Общий дедлайн в секундах на проверку всех псевдонимов.           |
| `SOCKET_TIMEOUT` | `float` | `5.0`        | Секунды ожидания TCP-соединения с одним узлом во время проверки. |
| `STACK_TIMEOUT`  | `float` | `10.0`       | Секунды ожидания полного цикла TCP + AMQP одного узла.           |

Полный пример настроек см. в разделе [Конфигурация](./configuration.md).
