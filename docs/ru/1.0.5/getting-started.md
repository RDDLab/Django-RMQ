---
title: Начало работы
order: 2
---

# Начало работы

## Требования

- Python >= 3.10
- Django >= 4.2
- RabbitMQ 3.13–4.3
- `pika==1.4.1` (устанавливается автоматически как зависимость)

## Установка

```bash
pip install django-rmq
```

## Регистрация приложения

Добавьте `'django_rmq'` в `INSTALLED_APPS` в вашем `settings.py`:

```python
INSTALLED_APPS = [
    # ...
    'django_rmq',
]
```

`RabbitMQAppConfig.ready()` читает `RABBITMQ_CONNECTIONS` при запуске и инициализирует менеджеры подключений и реестры
для каждого alias. Настройка должна присутствовать и быть непустой, иначе Django выбросит `ImproperlyConfigured` при
старте.

## Минимальная конфигурация

Добавьте блок `RABBITMQ_CONNECTIONS` хотя бы с одним alias. Все девять ключей обязательны:

```python
RABBITMQ_CONNECTIONS = {
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

См. [Конфигурацию](/ru/1.0.5/configuration.html) для полного справочника параметров и примеров чтения значений из переменных
окружения.

## Публикуем первое сообщение

Создайте `Producer` и вызовите `publish`. Очередь объявляется лениво при первой публикации:

```python
from django_rmq.producer import Producer

Producer(queue='orders').publish(body='{"order_id": 42}')
```

- `body` принимает `str` или `bytes`. Строки автоматически кодируются в UTF-8.
- По умолчанию каждое сообщение публикуется с `delivery_mode=2` (`persistence`) и `mandatory=True`.

Cм. [Продюсеры](/ru/1.0.5/producers.html) для routing keys, кастомных properties, режима exchange-only и стиля декоратора.

## Принимаем первое сообщения

### 1. Создание и регистрация консьюмера

Создайте `Consumer`, зарегистрируйте функцию-обработчик и добавьте консьюмер в реестр. Хорошее место для этого кода —
выделенный модуль `consumers.py` внутри вашего Django-приложения:

```python
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic,
    BasicProperties

from django_rmq.consumer import Consumer
from django_rmq.registries.registry import get_consumers_registry

consumer: Consumer = Consumer(queue='orders')


@consumer
def handle_order(
    ch: BlockingChannel,
    method: Basic.Deliver,
    props: BasicProperties,
    body: bytes,
) -> None:
    # process the message ...
    ch.basic_ack(delivery_tag=method.delivery_tag)


get_consumers_registry().register(consumer=consumer)
```

Библиотека **не** делает auto-ack сообщений при успехе. Каждый обработчик должен явно вызывать `ch.basic_ack(...)` или
`ch.basic_nack(...)`. Если обработчик выбрасывает необработанное исключение, консьюмер автоматически вызывает
`ch.basic_nack(requeue=False)`, чтобы сообщение попало в dead-letter exchange (если настроен) вместо бесконечного цикла.

### 2. Импорт модуля consumers в AppConfig.ready()

Django импортирует модули приложений лениво, поэтому модуль `consumers.py` нужно импортировать явно, чтобы консьюмер был
зарегистрирован до запуска `start_consumers`. Переопределите `ready()` в `AppConfig` вашего приложения:

```python
from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = 'orders'

    def ready(self) -> None:
        import orders.consumers  # noqa: F401
```

### 3. Запуск обработчика сообщений

```bash
uv run python manage.py start_consumers
```

Команда запускает по одному потоку на каждый зарегистрированный консьюмер, выводит сводную таблицу и корректно завершает
работу по сигналам `SIGTERM`/`SIGINT`.

## Где реализовывать консьюмеров

Держите определения консьюмеров в файле `consumers.py` (или пакете `consumers/`) в корне каждого Django-приложения,
которому принадлежит очередь. Импортируйте этот модуль в `AppConfig.ready()` приложения. Этот паттерн повторяет
стандартный способ подключения Django-сигналов.

## Следующие шаги

| Тема                                                                       | Страница                                               |
|----------------------------------------------------------------------------|--------------------------------------------------------|
| Полный справочник конфигурации                                             | [Конфигурация](/ru/1.0.5/configuration.html)                 |
| Продюсеры — режим декоратора, routing через exchange, кастомные properties | [Продюсеры](/ru/1.0.5/producers.html)                        |
| Консьюмеры — поведение при переподключении, DLX, prefetch                  | [Консьюмеры](/ru/1.0.5/consumers.html)                       |
| Объявление exchanges, очередей и bindings                                  | [Топология](/ru/1.0.5/topology.html)                         |
| Реестры и жизненный цикл AppConfig                                         | [Реестры](/ru/1.0.5/registries.html)                         |
| Management-команды                                                         | [Management-команды](/ru/1.0.5/management-commands.html)     |
| Гарантии надёжности                                                        | [Надёжность](/ru/1.0.5/reliability.html)                     |
| Несколько подключений к брокеру                                            | [Несколько подключений](/ru/1.0.5/multiple-connections.html) |
| Полный публичный API                                                       | [Справочник API](/ru/1.0.5/api-reference.html)               |
| Запуск и написание тестов                                                  | [Тестирование](/ru/1.0.5/testing.html)                       |
