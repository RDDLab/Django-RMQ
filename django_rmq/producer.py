import logging
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any

from pika import DeliveryMode
from pika.exceptions import (
    AMQPConnectionError,
    ChannelClosed,
    ChannelClosedByBroker,
    ConnectionClosed,
    StreamLostError,
)
from pika.spec import BasicProperties

from django_rmq.connections import get_connection_manager
from django_rmq.queues.queue_config import QueueConfig

logger = logging.getLogger('rabbitmq')

if TYPE_CHECKING:
    from pika.adapters.blocking_connection import BlockingChannel
    from pika.spec import Basic

    MessageCallback = Callable[[BlockingChannel, Basic.Deliver, BasicProperties, bytes], None]

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
    Publishes messages to RabbitMQ through a thread-local blocking channel.

    An instance is bound to a specific exchange + queue pair: both are set
    once at creation and used for every publish. An empty string in
    `exchange` means the default (direct) exchange.

    The queue is declared lazily — only on the first publish, not when the
    object is created. This allows creating a Producer ahead of time (e.g.
    at module level) without an active connection to the broker. The
    `_is_queue_declared` flag guarantees that `queue_declare` is called at
    most once per instance lifetime.

    When the channel or connection drops (exceptions from
    `_RECONNECTABLE_ERRORS`), exactly one retry is made with a new channel.
    If the retry also fails, the exception propagates upward.

    An instance can be used as a decorator (`@producer`): it then
    automatically publishes the return value of the wrapped function.
    """

    def __init__(
        self,
        exchange: str = '',
        queue: QueueConfig | str = '',
        using: str | None = None,
    ) -> None:
        """
        Initializes the Producer.

        :param exchange: RabbitMQ exchange name. An empty string is the default exchange.
        :param queue: Queue configuration (QueueConfig) or its name as a string. Used as
                      the default routing_key and declared on the broker on the first
                      publish. If an empty string is passed, queue declaration is
                      skipped (exchange-only mode with an explicit routing_key).
        :param using: Connection alias from `RABBITMQ_CONNECTIONS`. May be omitted when
                      exactly one connection is configured. Required when there are several.
        """
        self.exchange: str = exchange
        self.queue: str = str(queue)
        self._queue_config: QueueConfig | str = queue
        self._using: str | None = using
        # Lazy-declaration flag: True after the first successful queue_declare.
        self._is_queue_declared: bool = False

    def publish(
        self,
        body: str | bytes,
        routing_key: str | None = None,
        properties: BasicProperties | None = None,
    ) -> None:
        """
        Publishes a message to RabbitMQ.

        This method is the main entry point for sending messages. It prepares
        the message body and properties, then delegates the actual send to
        `_publish_once`. On network errors it automatically resets the cached
        channel and retries exactly once.

        Body preparation:
            - If `body` is a string, it is encoded to bytes (UTF-8).
            - Pika requires bytes; strings are not accepted directly.

        Properties preparation:
            - If `properties` is not passed, it is created with `delivery_mode=2`
              (persistent message) and `content_type='application/json'`.
            - If `properties` is passed but `delivery_mode` is unset, it is
              forced to `delivery_mode=2`. This guarantees the message is stored
              on the broker's disk and survives a broker restart.

        Retry logic:
            - The first attempt uses the existing thread-local channel.
            - On an exception from `_RECONNECTABLE_ERRORS` the channel is
              considered dead: `connection_manager.reset_producer_channel()` is
              called to drop the cache, then a second and final attempt is made
              with a new channel.
            - Any other exception propagates immediately without a retry.

        :param body: Message body as a string or bytes.
        :param routing_key: Routing key. If not passed, `self.queue` (the queue
                            name) is used.
        :param properties: AMQP message properties. If not passed, they are
                           built with persistent delivery mode.
        """
        source: str = 'Producer.publish'
        # An explicit routing_key takes priority; otherwise use the queue name.
        effective_routing_key: str = routing_key if routing_key is not None else self.queue
        if isinstance(body, str):
            body = body.encode()

        # delivery_mode=2 — persistent message: stored on the broker's disk.
        # Durable queues alone do not save messages across a broker restart
        # without this flag.
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
                # The channel or connection is broken — reset the cached channel
                # and make exactly one retry. If the retry also fails, the
                # exception flies to the outer except and is logged there.
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
        Performs a single attempt to publish a message through the thread-local channel.

        The method intentionally contains no retry logic — it makes exactly one
        `basic_publish` call and propagates any exception up to `publish`, which
        decides whether to reconnect and retry.

        Before publishing, `_ensure_queue_declared` is called to make sure the
        queue exists on the broker (lazily, only on the first call).

        The `mandatory=True` flag makes the broker return the message back
        (via `basic.return`) if no queue matches the routing_key, instead of
        silently dropping it.

        :param body: Message body in bytes.
        :param routing_key: Routing key.
        :param properties: AMQP message properties.
        """
        # Get the thread-local channel (created or reused).
        channel: BlockingChannel = get_connection_manager(using=self._using).get_producer_channel()
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
        Checks that the queue exists on the broker on the first call (passive mode).

        The method is idempotent over the instance lifetime: after the first
        successful declaration the `_is_queue_declared` flag is set to True, and
        subsequent calls return immediately without contacting the broker.

        If `self.queue` is an empty string (exchange-only mode), the method
        does nothing.

        passive=True is used: the broker returns the queue's current state
        without trying to create or modify it. This lets the producer publish
        to queues with any arguments (e.g. x-dead-letter-exchange) declared
        via setup_rabbitmq, without conflicting with them.

        :param channel: The active AMQP channel used for the check.
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

    def __call__(self, func: Callable[..., str | bytes | None]) -> Callable[..., str | bytes | None]:
        """
        Allows using a Producer instance as a function decorator.

        Wraps the function so that its return value is automatically published
        to the queue via `self.publish`. This lets you declaratively tie
        business logic to message sending without an explicit `publish` call
        inside the function:

            @producer
            def build_event(...) -> str:
                return json.dumps({...})

        Return-value contract:
            - `str` or `bytes` — published and returned to the caller.
            - `None` — publishing is skipped; the function "chose not to send".
            - Any other type — `TypeError` is raised. The decorator is
              intentionally strict: silent serialization of dict/list hides
              contract errors.

        :param func: The decorated function. Must return `str`, `bytes`, or `None`.
        :return: The wrapped function with the same signature, name, and docstring.
        """
        source: str = 'Producer.__call__'

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> str | bytes | None:
            result: str | bytes | None = func(*args, **kwargs)
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
