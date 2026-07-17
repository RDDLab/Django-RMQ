import logging
import random
import threading

from pika import BlockingConnection, ConnectionParameters, PlainCredentials
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPError

import django_rmq
from django_rmq.dto.rabbitmq_config import RabbitMQConfig
from django_rmq.utils import resolve_alias

logger = logging.getLogger('rabbitmq')


def get_connection_manager(using: str | None = None) -> 'RabbitMQConnectionManager':
    """
    Returns the connection manager for the given alias.

    :param using: Connection alias from `RABBITMQ_CONNECTIONS`. May be omitted when
                  exactly one connection is configured. Required when there are several.
    :return: The RabbitMQConnectionManager bound to the resolved alias.
    """
    return resolve_alias(mapping=django_rmq.connection_managers, using=using)


class RabbitMQConnectionManager:
    """
    Manages thread-local connections and the producer channel for RabbitMQ.

    Producer and Consumer get *separate* BlockingConnections per thread.
    Exactly one I/O loop owns a pika BlockingConnection; while
    Consumer.consume() drives that loop via process_data_events(), any
    concurrent operation on the same connection — whether a publish()
    from a handler or a heartbeat from another thread — corrupts the AMQP
    protocol stream and may hang or drop the connection. Splitting by
    role makes the "publish from a handler" pattern safe by construction.
    """

    def __init__(self, config: RabbitMQConfig) -> None:
        self.config: RabbitMQConfig = config
        credentials: PlainCredentials = PlainCredentials(
            username=config.user,
            password=config.password,
        )
        self._node_parameters: list[ConnectionParameters] = [
            ConnectionParameters(
                host=node.host,
                port=node.port,
                virtual_host=config.virtual_host,
                credentials=credentials,
                heartbeat=config.heartbeat,
                blocked_connection_timeout=config.blocked_connection_timeout,
            )
            for node in config.nodes
        ]
        self._shuffle_nodes: bool = config.shuffle_nodes
        self._local: threading.local = threading.local()

    def _build_connection_sequence(self) -> list[ConnectionParameters]:
        """
        Returns the node parameters to hand to a new BlockingConnection.

        A fresh copy is returned every time; when `shuffle_nodes` is enabled the
        copy is reshuffled so each connection attempt (initial or reconnect)
        prefers a different node, spreading clients across the cluster.

        :return: The (optionally shuffled) list of per-node ConnectionParameters.
        """
        sequence: list[ConnectionParameters] = list(self._node_parameters)
        if self._shuffle_nodes:
            random.shuffle(sequence)
        return sequence

    def _get_or_create_connection(self, attr: str, source: str, message: str) -> BlockingConnection:
        """
        Returns a thread-local connection, opening a new one if missing or closed.

        :param attr: Name of the thread-local attribute that caches the connection
                     (separate slots for the producer and consumer roles).
        :param source: Source identifier is used in the debug log when a new
                       connection is opened.
        :param message: Log message describing which connection is being created.
        :return: An open BlockingConnection cached on the current thread.
        """
        if not hasattr(self._local, attr) or not getattr(self._local, attr).is_open:
            sequence: list[ConnectionParameters] = self._build_connection_sequence()
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
            setattr(self._local, attr, BlockingConnection(parameters=sequence))
        return getattr(self._local, attr)

    def get_producer_connection(self) -> BlockingConnection:
        """
        Returns the thread-local connection dedicated to publishing.

        :return: An open BlockingConnection used only by producers on this thread.
        """
        return self._get_or_create_connection(
            attr='producer_connection',
            source='RabbitMQConnectionManager.get_producer_connection',
            message='Creating new producer connection',
        )

    def get_consumer_connection(self) -> BlockingConnection:
        """
        Returns the thread-local connection dedicated to consuming.

        :return: An open BlockingConnection used only by consumers on this thread.
        """
        return self._get_or_create_connection(
            attr='consumer_connection',
            source='RabbitMQConnectionManager.get_consumer_connection',
            message='Creating new consumer connection',
        )

    def get_producer_channel(self) -> BlockingChannel:
        """
        Returns the thread-local producer channel with publisher confirms enabled.

        Creates the channel (and its connection) on first use and reuses it
        afterward; a new one is opened automatically if the cached channel
        has been closed.

        :return: An open BlockingChannel configured with confirm_delivery().
        """
        _source: str = 'RabbitMQConnectionManager.get_producer_channel'
        connection: BlockingConnection = self.get_producer_connection()
        if not hasattr(self._local, 'producer_channel') or not self._local.producer_channel.is_open:
            logger.debug(
                {
                    'source': _source,
                    'message': 'Creating new producer channel',
                    'data': {},
                }
            )
            channel: BlockingChannel = connection.channel()
            # Publisher confirms — basic_publish raises UnroutableError /
            # NackError instead of silently dropping the message when the
            # broker cannot accept it.
            channel.confirm_delivery()
            self._local.producer_channel = channel
        return self._local.producer_channel

    def reset_producer_channel(self) -> None:
        """
        Drops the cached producer channel and connection. Call after a
        failed publication so the next publication reconnects.
        """
        _source: str = 'RabbitMQConnectionManager.reset_producer_channel'
        logger.debug({'source': _source, 'message': 'Resetting producer channel/connection', 'data': {}})

        channel: BlockingChannel | None = getattr(self._local, 'producer_channel', None)
        if channel is not None:
            try:
                if channel.is_open:
                    channel.close()
            except (AMQPError, OSError) as exc:
                logger.warning(
                    {
                        'source': _source,
                        'message': 'Failed to close producer channel',
                        'data': {'error': str(exc)},
                    }
                )
            delattr(self._local, 'producer_channel')

        connection: BlockingConnection | None = getattr(self._local, 'producer_connection', None)
        if connection is not None:
            try:
                if connection.is_open:
                    connection.close()
            except (AMQPError, OSError) as exc:
                logger.warning(
                    {
                        'source': _source,
                        'message': 'Failed to close producer connection',
                        'data': {'error': str(exc)},
                    }
                )
            delattr(self._local, 'producer_connection')
