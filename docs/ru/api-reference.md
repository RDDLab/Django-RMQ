---
title: Справочник API
order: 12
---

# Справочник API

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
from django_rmq.queues.queue_config import QueueConfig
```

`frozen dataclass` для декларативной конфигурации очереди.

```python
@dataclass(frozen=True)
class QueueConfig:
    name: str
    durable: bool = True
    dead_letter_exchange: str | None = None
    dead_letter_routing_key: str | None = None
```

| Поле                      | Тип           | По умолчанию | Описание                                                                          |
|---------------------------|---------------|--------------|-----------------------------------------------------------------------------------|
| `name`                    | `str`         | обязательное | Имя очереди. Также используется как `str(queue_config)`.                          |
| `durable`                 | `bool`        | `True`       | Очередь переживает перезапуск брокера.                                            |
| `dead_letter_exchange`    | `str \| None` | `None`       | Обменник, куда маршрутизируются dead-letter сообщения (`x-dead-letter-exchange`). |
| `dead_letter_routing_key` | `str \| None` | `None`       | Ключ маршрутизации для dead-letter сообщений (`x-dead-letter-routing-key`).       |

### Свойство `QueueConfig.arguments`

```python
@property
def arguments(self) -> dict[str, Any] | None
```

Строит словарь AMQP `arguments` для объявления очереди на основе полей dead-letter. Возвращает `None`, если ни одно из
полей не задано.

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
    host: str
    port: int
    virtual_host: str
    user: str
    password: str
    heartbeat: int
    blocked_connection_timeout: int
    reconnect_initial_backoff: float
    reconnect_max_backoff: float
```

| Поле                         | Тип     | Описание                                                                                  |
|------------------------------|---------|-------------------------------------------------------------------------------------------|
| `host`                       | `str`   | Хостнейм или IP брокера.                                                                  |
| `port`                       | `int`   | AMQP-порт.                                                                                |
| `virtual_host`               | `str`   | Виртуальный хост для подключения.                                                         |
| `user`                       | `str`   | Имя пользователя для `PlainCredentials`.                                                  |
| `password`                   | `str`   | Пароль для `PlainCredentials`.                                                            |
| `heartbeat`                  | `int`   | Интервал heartbeat в секундах.                                                            |
| `blocked_connection_timeout` | `int`   | Секунды ожидания, пока соединение заблокировано брокером.                                 |
| `reconnect_initial_backoff`  | `float` | Начальная задержка переподключения консьюмера в секундах.                                 |
| `reconnect_max_backoff`      | `float` | Максимальная задержка переподключения консьюмера (ограничение экспоненциальной задержки). |

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
`setup_registries` и `consumers_registries`.

**Raises:** `ImproperlyConfigured` — `RABBITMQ_CONNECTIONS` отсутствует или пуст.

---

## Глобальные переменные модуля (`django_rmq`)

```python
import django_rmq

django_rmq.connection_managers  # dict[str, RabbitMQConnectionManager] | None
django_rmq.setup_registries  # dict[str, SetupRegistry] | None
django_rmq.consumers_registries  # dict[str, ConsumersRegistry] | None
```

Все три имеют значение `None` до выполнения `RabbitMQAppConfig.ready()`. Используйте функции-аксессоры (
`get_connection_manager`, `get_consumers_registry`, `get_setup_registry`) вместо прямого обращения к этим словарям.

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

| Ключ                         | Тип     | Описание                                                                 |
|------------------------------|---------|--------------------------------------------------------------------------|
| `HOST`                       | `str`   | Хостнейм или IP брокера.                                                 |
| `PORT`                       | `int`   | AMQP-порт (обычно `5672`).                                               |
| `VIRTUAL_HOST`               | `str`   | Виртуальный хост (например, `'/'`).                                      |
| `USER`                       | `str`   | Имя пользователя для аутентификации.                                     |
| `PASSWORD`                   | `str`   | Пароль для аутентификации.                                               |
| `HEARTBEAT`                  | `int`   | Интервал heartbeat в секундах.                                           |
| `BLOCKED_CONNECTION_TIMEOUT` | `int`   | Секунды до таймаута заблокированного соединения.                         |
| `RECONNECT_INITIAL_BACKOFF`  | `float` | Начальная задержка переподключения консьюмера в секундах.                |
| `RECONNECT_MAX_BACKOFF`      | `float` | Максимальная задержка переподключения консьюмера (ограничение задержки). |

Все девять ключей обязательны для каждого псевдонима. Отсутствующие ключи вызывают `KeyError` в процессе
`AppConfig.ready()`. Полный пример настроек см. в разделе [Конфигурация](/ru/configuration.html).
