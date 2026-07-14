---
title: Надёжность
order: 9
---

# Надёжность

Django-RMQ построен на гарантии доставки **at-least-once**. Каждое архитектурное решение в библиотеке служит одной цели: сообщение, принятое `publish()`, должно в конечном счёте попасть к обработчику, а сбой обработчика не должен приводить к молчаливой потере сообщения.

На этой странице описан каждый механизм надёжности, его расположение в коде, а также то, что нужно (или не нужно) делать в вашем коде, чтобы им воспользоваться.

---

## Подтверждения публикации

На каждом канале продюсера включены подтверждения публикации. Канал открывается с `confirm_delivery()`, поэтому каждый вызов `basic_publish` блокируется до получения подтверждения от брокера:

```python
# django_rmq/connections.py
channel.confirm_delivery()
```

Это означает, что `Producer.publish()` синхронен относительно принятия сообщения брокером. Если брокер не может принять сообщение — например, потому что ни одна очередь не соответствует ключу маршрутизации — он выбрасывает `pika.exceptions.UnroutableError` вместо молчаливого сброса сообщения.

---

## Обязательная маршрутизация

`basic_publish` всегда вызывается с `mandatory=True`:

```python
# django_rmq/producer.py
channel.basic_publish(
    exchange=self.exchange,
    routing_key=routing_key,
    body=body,
    properties=properties,
    mandatory=True,
)
```

В сочетании с подтверждениями публикации это гарантирует, что публикация с ключом маршрутизации, не совпадающим ни с одной привязанной очередью, немедленно выбросит `UnroutableError`. Набор интеграционных тестов проверяет это поведение против реального брокера:

```python
from django_rmq.producer import Producer
from pika.exceptions import UnroutableError

# Publishing to the default exchange with a routing key that matches no queue
# raises UnroutableError (not a silent drop).
producer: Producer = Producer(exchange='', queue='')

with pytest.raises(UnroutableError):
    producer.publish(body=b'nowhere', routing_key='no-such-queue')
```

---

## Persistence-сообщения

Каждое сообщение, опубликованное через `Producer.publish()`, помечается как персистентное (`delivery_mode=2`). Если `BasicProperties` не переданы, библиотека создаёт их с `delivery_mode=DeliveryMode.Persistent`. Если вы передаёте собственные `BasicProperties` без указания `delivery_mode`, библиотека также принудительно устанавливает его в персистентный режим:

```python
from django_rmq.producer import Producer
from pika.spec import BasicProperties

producer: Producer = Producer(queue='orders')

# delivery_mode is forced to 2 regardless of whether you pass properties or not.
producer.publish(body='{"order_id": 42}')

# Custom properties — delivery_mode will still be forced to 2.
props: BasicProperties = BasicProperties(content_type='application/json')
producer.publish(body='{"order_id": 42}', properties=props)
```

Персистентные сообщения переживают перезапуск брокера при условии, что очередь также является долговечной (durable). `QueueConfig` по умолчанию является durable; обычная строковая очередь объявляется durable при потреблении через `Consumer`.

---

## Самовосстановление продюсера (одна попытка ретрая)

Когда кешированный канал или соединение продюсера оказываются разорванными в момент публикации, продюсер сбрасывает их и выполняет ровно одну повторную попытку. Набор ошибок, при которых инициируется повтор, фиксирован:

```python
# django_rmq/producer.py
_RECONNECTABLE_ERRORS = (
    AMQPConnectionError,
    ConnectionClosed,
    ChannelClosed,
    ChannelClosedByBroker,
    StreamLostError,
    ConnectionResetError,
)
```

При первой попытке, если возникает одна из этих ошибок, `reset_producer_channel()` удаляет кешированный канал и соединение. Вторая попытка открывает новый канал и повторяет ту же публикацию. Если повтор также завершается ошибкой, исключение распространяется к вызывающему коду.

Набор интеграционных тестов проверяет это, принудительно закрывая соединение продюсера через Management API:

```python
from django_rmq.producer import Producer

producer: Producer = Producer(queue='orders')

producer.publish(body=b'first')   # opens the producer connection

# force-close the connection from outside...

producer.publish(body=b'second')  # transparently reconnects and succeeds
```

**Выполняется ровно одна попытка повтора.** Никакого цикла или экспоненциальной задержки на стороне продюсера нет. Если брокер недоступен после повтора, исключение распространяется.

---

## Переподключение консьюмера с экспоненциальной задержкой

Консьюмер автоматически переподключается при любой ошибке из `_RECONNECTABLE_ERRORS`. После каждого разрыва соединения задержка перед повтором удваивается до достижения `reconnect_max_backoff`:

```python
# django_rmq/consumer.py
backoff = min(backoff * 2, max_backoff)
```

Значения задержки берутся из конфигурации alias'а соединения (`RECONNECT_INITIAL_BACKOFF` и `RECONNECT_MAX_BACKOFF`). Их можно переопределить для конкретного консьюмера:

```python
from django_rmq.consumer import Consumer
from django_rmq.queues.queue_config import QueueConfig

consumer: Consumer = Consumer(
    queue=QueueConfig(name='orders'),
    reconnect_initial_backoff=0.5,  # seconds; defaults to alias config value
    reconnect_max_backoff=60.0,     # seconds; defaults to alias config value
)
```

Во время ожидания перед переподключением используется `stop_event.wait(timeout=backoff)`, так что сигнал завершения немедленно пробуждает консьюмер, не дожидаясь истечения полной задержки.

Неустранимая ошибка (любое исключение, не входящее в `_RECONNECTABLE_ERRORS`), логируется на уровне `error` и пробрасывается, завершая цикл потребления.

---

## Dead-letter при ошибке обработчика

Когда обработчик выбрасывает исключение, `Consumer._dispatch` логирует ошибку и вызывает `basic_nack(requeue=False)`:

```python
# django_rmq/consumer.py — _dispatch
try:
    handler(ch, method, props, body)
except Exception as exc:
    logger.error(...)
    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
```

`requeue=False` указывает брокеру направить сообщение в dead-letter вместо возврата в очередь. Если очередь была объявлена с `dead_letter_exchange`, сообщение маршрутизируется туда. Без DLX брокер его отбрасывает.

Такое поведение намеренно: бесконечный цикл повторной очереди на «ядовитом» сообщении может насытить очередь и вытеснить нормальных консьюмеров. Настройте DLX + DLQ для любой очереди, где необходимо инспектировать упавшие сообщения.

Подробнее о том, как объявить dead-letter exchange с `QueueConfig`, смотрите в разделе [Топология](/ru/1.0.4/topology.html).

**Обработчик должен явно подтверждать каждое успешно обработанное сообщение.** Библиотека не выполняет auto-ack. Пропущенный `basic_ack` оставляет сообщение неподтверждённым, и оно будет повторно доставлено после отключения консьюмера.

```python
from typing import Any
from pika.adapters.blocking_connection import BlockingChannel

@consumer
def handle_order(
    ch: BlockingChannel,
    method: Any,
    props: Any,
    body: bytes,
) -> None:
    process(body)
    ch.basic_ack(delivery_tag=method.delivery_tag)  # required
```

Интеграционный тест проверяет полный путь — обработчик выбрасывает исключение, брокер маршрутизирует сообщение в DLQ:

```python
from django_rmq.consumer import Consumer
from django_rmq.producer import Producer
from django_rmq.queues.queue_config import QueueConfig

queue_config: QueueConfig = QueueConfig(
    name='orders',
    dead_letter_exchange='dlx-orders',
    dead_letter_routing_key='dlq-orders',
)
consumer: Consumer = Consumer(queue=queue_config)

@consumer
def handler(ch: BlockingChannel, method: Any, props: Any, body: bytes) -> None:
    raise ValueError('boom')   # nacked -> routed to dlx-orders / dlq-orders

Producer(queue=queue_config).publish(body='{"will": "fail"}')
```

---

## Соединения с базой данных Django

Потоки консьюмеров являются долгоживущими. Пул соединений с базой данных Django имеет серверные таймауты простоя; после периода неактивности сервер закрывает сокет, но поток Django по-прежнему держит ссылку на мёртвое соединение.

`Consumer._dispatch` вызывает `close_old_connections()` перед каждой диспетчеризацией сообщения:

```python
# django_rmq/consumer.py — _dispatch
from django.db import close_old_connections

close_old_connections()
try:
    handler(ch, method, props, body)
```

Это заставляет Django удалять устаревшие соединения, чтобы ORM восстанавливал их лениво при следующем запросе к базе данных, предотвращая `OperationalError: server closed the connection unexpectedly` в обработчиках.

---

## Модель потокобезопасности

Django-RMQ использует `threading.local`, чтобы дать каждому потоку собственное соединение для продюсера и консьюмера:

```python
# django_rmq/connections.py
self._local: threading.local = threading.local()
```

Разделение соединений продюсера и консьюмера намеренно. `BlockingConnection` владеет ровно одним I/O-циклом. Пока `Consumer.consume()` управляет этим циклом через `process_data_events()`, любой параллельный `publish()` на том же соединении привёл бы к повреждению потока протокола AMQP. Раздельные соединения делают паттерн публикации из обработчика консьюмера безопасным по конструкции.

| Тип потока | Слот соединения | Примечания |
|---|---|---|
| Поток консьюмера | `_local.consumer_connection` | Принадлежит `_run_session`; закрывается по завершении сессии |
| Любой другой поток | `_local.producer_connection` + `_local.producer_channel` | Создаётся при первой публикации; сбрасывается при восстанавливаемой ошибке |

Не передавайте экземпляр `Producer` или `Consumer` между потоками. Создавайте по одному экземпляру на поток или используйте команду управления `start_consumers`, которая сама управляет потоками.
