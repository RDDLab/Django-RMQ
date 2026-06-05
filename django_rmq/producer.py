import logging
from functools import wraps
from typing import (
    Any,
    Callable,
    Optional,
    Union,
    TYPE_CHECKING
)

from pika import DeliveryMode
from pika.spec import BasicProperties
from pika.exceptions import (
    AMQPConnectionError,
    ChannelClosed,
    ChannelClosedByBroker,
    ConnectionClosed,
    StreamLostError,
)

from django_rmq.connections import get_connection_manager
from django_rmq.queues.queue_config import QueueConfig

logger = logging.getLogger('rabbitmq')

if TYPE_CHECKING:
    from pika.adapters.blocking_connection import BlockingChannel

    MessageCallback = Callable[['BlockingChannel', 'Basic.Deliver', 'BasicProperties', bytes], None]

_RECONNECTABLE_ERRORS = (
    AMQPConnectionError,
    ConnectionClosed,
    ChannelClosed,
    ChannelClosedByBroker,
    StreamLostError,
    ConnectionResetError,
)


class Producer:
    """
    Публикует сообщения в RabbitMQ через thread-local блокирующий канал.

    Экземпляр привязан к конкретной связке exchange + queue: оба параметра
    задаются один раз при создании и используются во всех публикациях.
    Пустая строка в `exchange` означает обменник по умолчанию (direct).

    Очередь объявляется лениво — только при первой публикации, а не при
    создании объекта. Это позволяет создавать Producer заранее (например,
    на уровне модуля) без активного соединения с брокером. Флаг
    `_is_queue_declared` гарантирует, что `queue_declare` вызывается не
    более одного раза на время жизни экземпляра.

    При разрыве канала или соединения (исключения из `_RECONNECTABLE_ERRORS`)
    делается ровно одна повторная попытка с новым каналом. Если повтор тоже
    провалился — исключение пробрасывается выше.

    Экземпляр можно использовать как декоратор (`@producer`): тогда он
    автоматически публикует возвращаемое значение обёрнутой функции.
    """

    def __init__(
        self,
        exchange: str = '',
        queue: Union[QueueConfig, str] = '',
        using: Optional[str] = None,
    ) -> None:
        """
        Инициализирует Producer.

        :param exchange: Имя обменника RabbitMQ. Пустая строка — обменник по умолчанию.
        :param queue: Конфигурация очереди (QueueConfig) или её имя строкой. Используется
                      как routing_key по умолчанию и объявляется на брокере при первой
                      публикации. Если передана пустая строка — объявление очереди
                      пропускается (режим работы только через exchange с явным routing_key).
        :param using: Alias соединения из `RABBITMQ_CONNECTIONS`. Если сконфигурировано
                      ровно одно соединение — можно опустить. При нескольких — обязателен.
        """
        self.exchange: str = exchange
        self.queue: str = str(queue)
        self._queue_config: Union[QueueConfig, str] = queue
        self._using: Optional[str] = using
        # Флаг ленивого объявления: True после первого успешного queue_declare.
        self._is_queue_declared: bool = False

    def publish(
        self,
        body: Union[str, bytes],
        routing_key: Optional[str] = None,
        properties: Optional[BasicProperties] = None,
    ) -> None:
        """
        Публикует сообщение в RabbitMQ.

        Метод — основная точка входа для отправки сообщений. Он выполняет
        подготовку тела и свойств сообщения, а затем делегирует фактическую
        отправку методу `_publish_once`. При сетевых ошибках автоматически
        сбрасывает кешированный канал и повторяет попытку ровно один раз.

        Подготовка тела:
            - Если `body` — строка, она кодируется в bytes (UTF-8).
            - Pika требует bytes; строки не принимаются напрямую.

        Подготовка свойств:
            - Если `properties` не передан — создаётся с `delivery_mode=2`
              (персистентное сообщение) и `content_type='application/json'`.
            - Если `properties` передан, но `delivery_mode` не выставлен —
              принудительно устанавливается `delivery_mode=2`. Это гарантирует,
              что сообщение сохранится на диске брокера и переживёт его перезапуск.

        Логика повтора:
            - Первая попытка выполняется через существующий thread-local канал.
            - При исключении из `_RECONNECTABLE_ERRORS` канал считается мёртвым:
              вызывается `connection_manager.reset_producer_channel()` для удаления кеша, после чего
              делается вторая и последняя попытка с новым каналом.
            - Любые другие исключения пробрасываются немедленно без повтора.

        :param body: Тело сообщения в виде строки или байтов.
        :param routing_key: Ключ маршрутизации. Если не передан, используется
                            `self.queue` (имя очереди).
        :param properties: AMQP-свойства сообщения. Если не переданы — формируются
                           с персистентным режимом доставки.
        """
        source: str = 'Producer.publish'
        # Явный routing_key имеет приоритет; иначе используем имя очереди.
        effective_routing_key: str = routing_key if routing_key is not None else self.queue
        if isinstance(body, str):
            body = body.encode()

        # delivery_mode=2 — персистентное сообщение: сохраняется на диск брокера.
        # Durable-очереди сами по себе не спасают сообщения при перезапуске брокера
        # без этого флага.
        properties = properties or BasicProperties(content_type='application/json')
        if properties.delivery_mode is None:
            properties.delivery_mode = DeliveryMode.Persistent.value

        logger.debug(
            {
                'source': source,
                'message': 'Publishing message',
                'data': {
                    'exchange': self.exchange,
                    'routing_key': effective_routing_key,
                    'body_length': len(body),
                },
            }
        )

        try:
            try:
                self._publish_once(
                    body=body,
                    routing_key=effective_routing_key,
                    properties=properties,
                )
            except _RECONNECTABLE_ERRORS as exc:
                # Канал или соединение разорваны — сбрасываем кешированный канал
                # и делаем ровно одну повторную попытку. Если повтор тоже упадёт,
                # исключение улетит во внешний except и будет залогировано там.
                logger.warning(
                    {
                        'source': source,
                        'message': 'Publish failed on cached channel — resetting and retrying',
                        'data': {
                            'exchange': self.exchange,
                            'routing_key': effective_routing_key,
                            'error': str(exc),
                        },
                    }
                )
                get_connection_manager(using=self._using).reset_producer_channel()
                self._publish_once(
                    body=body,
                    routing_key=effective_routing_key,
                    properties=properties,
                )
        except Exception as exc:
            logger.error(
                {
                    'source': source,
                    'message': 'Failed to publish message',
                    'data': {
                        'exchange': self.exchange,
                        'routing_key': effective_routing_key,
                        'error': str(exc),
                    },
                }
            )
            raise

    def _publish_once(
        self,
        body: bytes,
        routing_key: str,
        properties: BasicProperties,
    ) -> None:
        """
        Выполняет одну попытку публикации сообщения через thread-local канал.

        Метод намеренно не содержит логики повтора — он делает ровно один вызов
        `basic_publish` и пробрасывает любое исключение наверх, в `publish`,
        который решает, нужно ли переподключаться и повторять.

        Перед публикацией вызывается `_ensure_queue_declared`, чтобы убедиться,
        что очередь существует на брокере (лениво, только при первом вызове).

        Флаг `mandatory=True` заставляет брокер вернуть сообщение обратно
        (через `basic.return`), если ни одна очередь не соответствует routing_key,
        вместо того чтобы молча его потерять.

        :param body: Тело сообщения в байтах.
        :param routing_key: Ключ маршрутизации.
        :param properties: AMQP-свойства сообщения.
        """
        # Получаем thread-local канал (создаётся или переиспользуется).
        channel: 'BlockingChannel' = get_connection_manager(using=self._using).get_producer_channel()
        self._ensure_queue_declared(channel=channel)
        channel.basic_publish(
            exchange=self.exchange,
            routing_key=routing_key,
            body=body,
            properties=properties,
            mandatory=True,
        )

    def _ensure_queue_declared(self, channel: 'BlockingChannel') -> None:
        """
        Проверяет существование очереди на брокере при первом вызове (passive-режим).

        Метод идемпотентен в рамках жизни экземпляра: после первого успешного
        объявления флаг `_is_queue_declared` выставляется в True, и последующие
        вызовы немедленно возвращаются без обращения к брокеру.

        Если `self.queue` пустая строка (режим работы только через exchange),
        метод ничего не делает.

        Используется passive=True: брокер возвращает текущее состояние очереди
        без попытки её создать или изменить. Это позволяет продюсеру публиковать
        в очереди с любыми аргументами (например, x-dead-letter-exchange),
        объявленными через setup_rabbitmq, не вступая с ними в конфликт.

        :param channel: Активный AMQP-канал, через который выполняется проверка.
        """
        if not self.queue or self._is_queue_declared:
            return
        if isinstance(self._queue_config, QueueConfig):
            channel.queue_declare(
                queue=self.queue,
                durable=self._queue_config.durable,
                arguments=self._queue_config.arguments,  # type: ignore[arg-type]
            )
        else:
            channel.queue_declare(queue=self.queue, passive=True)
        self._is_queue_declared = True

    def __call__(self, func: Callable[..., Union[str, bytes, None]]) -> Callable[..., Union[str, bytes, None]]:
        """
        Позволяет использовать экземпляр Producer как декоратор функции.

        Обёртывает функцию так, что её возвращаемое значение автоматически
        публикуется в очередь через `self.publish`. Это позволяет декларативно
        связать бизнес-логику с отправкой сообщений без явного вызова `publish`
        внутри функции:

            @producer
            def build_event(...) -> str:
                return json.dumps({...})

        Контракт возвращаемого значения:
            - `str` или `bytes` — публикуется и возвращается вызывающему.
            - `None` — публикация пропускается; функция «решила не отправлять».
            - Любой другой тип — выбрасывается `TypeError`. Декоратор намеренно
              строг: молчаливая сериализация dict/list скрывает ошибки контракта.

        :param func: Декорируемая функция. Должна возвращать `str`, `bytes` или `None`.
        :return: Обёрнутая функция с той же сигнатурой, именем и docstring.
        """
        source: str = 'Producer.__call__'

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Union[str, bytes, None]:
            result: Union[str, bytes, None] = func(*args, **kwargs)
            if result is None:
                return None

            if not isinstance(result, (str, bytes)):
                raise TypeError(
                    f'Producer-decorated function {func.__name__!r} must return str | bytes | None, '
                    f'got {type(result).__name__}'
                )
            logger.debug(
                {
                    'source': source,
                    'message': 'Auto-publishing function return value',
                    'data': {'func': func.__name__},
                }
            )
            self.publish(body=result)

            return result

        return wrapper
