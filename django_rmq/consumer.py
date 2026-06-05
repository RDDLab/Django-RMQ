import functools
import logging
import threading
from typing import (
    Callable,
    Optional,
    Union,
    TYPE_CHECKING,
)

from django.db import close_old_connections
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
    from pika.adapters.blocking_connection import (
        BlockingChannel,
        BlockingConnection
    )
    from pika.spec import (
        Basic,
        BasicProperties
    )

_RECONNECTABLE_ERRORS = (
    AMQPConnectionError,
    ConnectionClosed,
    ChannelClosed,
    ChannelClosedByBroker,
    StreamLostError,
    ConnectionResetError,
)

MessageCallback = Callable[['BlockingChannel', 'Basic.Deliver', 'BasicProperties', bytes], None]


class Consumer:
    """
    Потребляет сообщения из одной очереди RabbitMQ с одним зарегистрированным
    обработчиком. Цикл потребления переподключается при временных AMQP-ошибках
    с экспоненциальной задержкой (ограниченной `reconnect_max_backoff`), опрашивает
    `stop_event` примерно раз в секунду для отзывчивого завершения работы и
    сбрасывает устаревшие Django DB-соединения перед каждой диспетчеризацией
    (передачи обработки зарегистрированному хендлеру).
    """

    def __init__(
        self,
        queue: Union[QueueConfig, str],
        prefetch_count: int = 1,
        reconnect_initial_backoff: Optional[float] = None,
        reconnect_max_backoff: Optional[float] = None,
        using: Optional[str] = None,
    ) -> None:
        """
        :param using: Alias соединения из `RABBITMQ_CONNECTIONS`. Если сконфигурировано
                      ровно одно соединение — можно опустить. При нескольких — обязателен.
        :param reconnect_initial_backoff: Переопределение начальной задержки. Если не
                      передано — берётся из конфига соответствующего соединения.
        :param reconnect_max_backoff: Переопределение максимальной задержки. Если не
                      передано — берётся из конфига соответствующего соединения.
        """
        self.queue: str = str(queue)
        self._queue_config: Union[QueueConfig, str] = queue
        self._prefetch_count: int = prefetch_count
        self._using: Optional[str] = using

        config = get_connection_manager(using=using).config
        self._reconnect_initial_backoff: float = (  # noqa
            reconnect_initial_backoff if reconnect_initial_backoff is not None
            else config.reconnect_initial_backoff
        )
        self._reconnect_max_backoff: float = (  # noqa
            reconnect_max_backoff if reconnect_max_backoff is not None
            else config.reconnect_max_backoff
        )
        self._handler: Optional['MessageCallback'] = None

    def handler(self, func: 'MessageCallback') -> 'MessageCallback':
        """
        Регистрирует callback для входящих сообщений.
        """
        if self._handler is not None:
            raise RuntimeError(
                f'Consumer for queue {self.queue!r} already has a handler'
            )
        self._handler = func
        return func

    def __call__(self, func: 'MessageCallback') -> 'MessageCallback':
        """
        Сокращённый вариант `@consumer.handler`.
        """
        return self.handler(func=func)

    def consume(self, stop_event: Optional[threading.Event] = None) -> None:
        """
        Запускает потребление сообщений с переподключением при временных AMQP-ошибках.

        При восстанавливаемой ошибке:
        1. Логирует предупреждение;
        2. Ожидает `backoff` секунд; stop_event.wait позволяет мгновенно завершить работу во время ожидания.
        3. Удваивает задержку до `reconnect_max_backoff`, затем повторяет попытку.
        4. Цикл завершается при установке stop_event или при возникновении невосстанавливаемой ошибки.
        В этом случае stop_event.wait немедленно пробудится -> управление перейдёт к
        `while not stop_event.is_set()`
        """
        source: str = 'Consumer.consume'
        handler: Optional['MessageCallback'] = self._handler
        if handler is None:
            logger.warning(
                {
                    'source': source,
                    'message': 'No handler registered — consumer will not start',
                    'data': {'queue': self.queue},
                }
            )
            return

        stop_event = stop_event if stop_event is not None else threading.Event()
        backoff: float = self._reconnect_initial_backoff

        while not stop_event.is_set():
            try:
                self._run_session(handler=handler, stop_event=stop_event)
                return
            except _RECONNECTABLE_ERRORS as exc:
                logger.warning(
                    {
                        'source': source,
                        'message': 'Consumer disconnected — will reconnect',
                        'data': {
                            'queue': self.queue,
                            'backoff_seconds': backoff,
                            'error': str(exc),
                        },
                    }
                )
                stop_event.wait(timeout=backoff)
                backoff = min(backoff * 2, self._reconnect_max_backoff)
            except Exception as exc:
                logger.error(
                    {
                        'source': source,
                        'message': 'Consumer encountered an unrecoverable error',
                        'data': {
                            'queue': self.queue,
                            'error': str(exc)
                        },
                    }
                )
                raise

    def _run_session(
        self,
        handler: 'MessageCallback',
        stop_event: threading.Event,
    ) -> None:
        """
        Один цикл: подключение → потребление → отключение. Возвращает управление при
        срабатывании stop_event; выбрасывает восстанавливаемую AMQP-ошибку для запуска
        внешнего цикла с задержкой переподключения.
        """
        source: str = 'Consumer._run_session'
        connection: 'BlockingConnection' = get_connection_manager(using=self._using).get_consumer_connection()
        channel: 'BlockingChannel' = connection.channel()
        try:
            self._declare_queue(channel=channel)
            channel.basic_qos(prefetch_count=self._prefetch_count)
            channel.basic_consume(
                queue=self.queue,
                on_message_callback=functools.partial(self._dispatch, handler),
            )
            logger.info(
                {
                    'source': source,
                    'message': 'Waiting for messages',
                    'data': {
                        'queue': self.queue,
                        'prefetch_count': self._prefetch_count,
                        'handler': handler.__name__,
                    },
                }
            )
            while not stop_event.is_set():
                connection.process_data_events(time_limit=1)
            logger.info(
                {
                    'source': source,
                    'message': 'Stop event received — leaving consume loop',
                    'data': {'queue': self.queue},
                }
            )
        finally:
            if channel.is_open:
                channel.stop_consuming()
                channel.close()

    def _declare_queue(self, channel: 'BlockingChannel') -> None:
        if isinstance(self._queue_config, QueueConfig):
            channel.queue_declare(
                queue=self.queue,
                durable=self._queue_config.durable,
                arguments=self._queue_config.arguments,  # type: ignore[arg-type]
            )
        else:
            channel.queue_declare(queue=self.queue, durable=True)

    def _dispatch(
        self,
        handler: 'MessageCallback',
        ch: 'BlockingChannel',
        method: 'Basic.Deliver',
        props: 'BasicProperties',
        body: bytes,
    ) -> None:
        source: str = 'Consumer._dispatch'
        # Долгоживущие потоки-потребители иначе удерживают мёртвые
        # Postgres-сокеты после срабатывания серверного таймаута простоя.
        close_old_connections()
        try:
            handler(ch, method, props, body)
        except Exception as exc:
            logger.error(
                {
                    'source': source,
                    'message': 'Handler raised — nacking without requeue (DLX if configured)',
                    'data': {
                        'queue': self.queue,
                        'delivery_tag': method.delivery_tag,
                        'error': str(exc),
                    },
                }
            )
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
