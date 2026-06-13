import functools
import logging
import threading
from collections.abc import Callable
from typing import (
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
    from pika.adapters.blocking_connection import BlockingChannel, BlockingConnection
    from pika.spec import Basic, BasicProperties

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
    Consumes messages from a single RabbitMQ queue with one registered
    handler. The consume loop reconnects on transient AMQP errors with
    exponential backoff (capped at `reconnect_max_backoff`), polls
    `stop_event` roughly once per second for responsive shutdown, and
    closes stale Django DB connections before each dispatch (handing the
    message off to the registered handler).
    """

    def __init__(
        self,
        queue: QueueConfig | str,
        prefetch_count: int = 1,
        reconnect_initial_backoff: float | None = None,
        reconnect_max_backoff: float | None = None,
        using: str | None = None,
    ) -> None:
        """
        Initializes the Consumer.

        :param queue: Queue configuration (QueueConfig) or its name as a string.
                      Determines the queue to consume from and how it is declared
                      on the broker (passively for a plain string, actively with
                      arguments for a QueueConfig).
        :param prefetch_count: Maximum number of unacknowledged messages the broker
                      delivers at once (basic_qos). Defaults to 1 for fair dispatch.
        :param reconnect_initial_backoff: Override for the initial reconnect delay
                      in seconds. If not passed, taken from the connection's config.
        :param reconnect_max_backoff: Override for the maximum reconnect delay in
                      seconds. If not passed, taken from the connection's config.
        :param using: Connection alias from `RABBITMQ_CONNECTIONS`. May be omitted when
                      exactly one connection is configured. Required when there are several.
        """
        self.queue: str = str(queue)
        self._queue_config: QueueConfig | str = queue
        self._prefetch_count: int = prefetch_count
        self._using: str | None = using

        # Backoff overrides are read lazily — the effective values are
        # resolved from the connection config in consume(), not in __init__.
        # This allows creating a Consumer at module level (before
        # AppConfig.ready() has initialized django_rmq), like Producer.
        self._reconnect_initial_backoff_override: float | None = reconnect_initial_backoff
        self._reconnect_max_backoff_override: float | None = reconnect_max_backoff
        self._handler: MessageCallback | None = None

    @property
    def prefetch_count(self) -> int:
        """
        Maximum number of unacknowledged messages the broker delivers at once.
        """
        return self._prefetch_count

    @property
    def using(self) -> str | None:
        """
        Connection alias the consumer is bound to, or None when the single
        configured connection is used implicitly.
        """
        return self._using

    @property
    def handler_name(self) -> str:
        """
        Name of the registered message handler, or 'unregistered' if none has
        been attached yet.
        """
        return self._handler.__name__ if self._handler is not None else 'unregistered'

    def handler(self, func: 'MessageCallback') -> 'MessageCallback':
        """
        Registers a callback for incoming messages.

        :param func: The callback invoked for every delivered message. It receives
                     the channel, the delivery method, the message properties, and
                     the raw body bytes.
        :return: The same `func`, unchanged, so it can be used as a decorator.
        :raises RuntimeError: If a handler has already been registered.
        """
        if self._handler is not None:
            raise RuntimeError(f'Consumer for queue {self.queue!r} already has a handler')
        self._handler = func
        return func

    def __call__(self, func: 'MessageCallback') -> 'MessageCallback':
        """
        Shorthand for `@consumer.handler`.

        :param func: The callback to register as the message handler.
        :return: The same `func`, unchanged, so it can be used as a decorator.
        """
        return self.handler(func=func)

    def consume(self, stop_event: threading.Event | None = None) -> None:
        """
        Starts consuming messages, reconnecting on transient AMQP errors.

        On a recoverable error:
        1. Logs a warning;
        2. Waits `backoff` seconds; stop_event.wait allows instant shutdown during the wait.
        3. Doubles the delay up to `reconnect_max_backoff`, then retries.
        4. The loop ends when stop_event is set or an unrecoverable error occurs.
        In that case stop_event.wait wakes up immediately -> control passes to
        `while not stop_event.is_set()`

        :param stop_event: Event used to request a graceful shutdown. When set, the
                           consume loop exits at the next poll (roughly once per
                           second) and during any reconnect backoff wait. If not
                           passed, a fresh internal Event is created (never set,
                           so the consumer runs until an unrecoverable error).
        """
        source: str = 'Consumer.consume'
        handler: MessageCallback | None = self._handler
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
        config = get_connection_manager(using=self._using).config
        initial_backoff: float = (
            self._reconnect_initial_backoff_override
            if self._reconnect_initial_backoff_override is not None
            else config.reconnect_initial_backoff
        )
        max_backoff: float = (
            self._reconnect_max_backoff_override
            if self._reconnect_max_backoff_override is not None
            else config.reconnect_max_backoff
        )
        backoff: float = initial_backoff

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
                backoff = min(backoff * 2, max_backoff)
            except Exception as exc:
                logger.error(
                    {
                        'source': source,
                        'message': 'Consumer encountered an unrecoverable error',
                        'data': {'queue': self.queue, 'error': str(exc)},
                    }
                )
                raise

    def _run_session(
        self,
        handler: 'MessageCallback',
        stop_event: threading.Event,
    ) -> None:
        """
        One cycle: connect → consume → disconnect. Returns control when
        stop_event fires; raises a recoverable AMQP error to trigger the
        outer loop with its reconnect delay.

        :param handler: The registered callback invoked for each delivered message.
        :param stop_event: Event polled once per second; when set, the session
                           leaves its consume loop and closes the channel cleanly.
        """
        source: str = 'Consumer._run_session'
        connection: BlockingConnection = get_connection_manager(using=self._using).get_consumer_connection()
        channel: BlockingChannel = connection.channel()
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
        """
        Declares the queue on the broker before consuming.

        For a QueueConfig the queue is declared actively with its durability and
        arguments (e.g. dead-letter routing). For a plain string name the queue is
        declared durable with default arguments.

        :param channel: The active AMQP channel used for the declaration.
        """
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
        """
        Hands a single delivery to the registered handler.

        Refreshes Django DB connections first, then calls the handler. If the
        handler raises, the message is nacked without requeue so it goes to the
        dead-letter exchange (if configured) instead of being redelivered forever.

        :param handler: The registered callback to invoke for this message.
        :param ch: The channel the message was delivered on (used to ack/nack).
        :param method: Delivery metadata, including the delivery_tag.
        :param props: AMQP message properties of the delivery.
        :param body: Raw message body bytes.
        """
        source: str = 'Consumer._dispatch'
        # Long-lived consumer threads otherwise hold dead Postgres sockets
        # after the server-side idle timeout fires.
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
