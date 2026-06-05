import logging
import threading
from typing import Optional

from pika import (
    BlockingConnection,
    ConnectionParameters,
    PlainCredentials
)
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPError

import django_rmq
from django_rmq.utils import resolve_alias
from django_rmq.dto.rabbitmq_config import RabbitMQConfig

logger = logging.getLogger('rabbitmq')


def get_connection_manager(using: Optional[str] = None) -> 'RabbitMQConnectionManager':
    return resolve_alias(mapping=django_rmq.connection_managers, using=using)


class RabbitMQConnectionManager:
    """
    Управляет thread-local соединениями и producer-каналом для RabbitMQ.

    Producer и Consumer получают *отдельные* BlockingConnection на поток.
    pika BlockingConnection принадлежит ровно одному I/O-циклу; пока
    Consumer.consume() крутит этот цикл через process_data_events(), любая
    параллельная операция над тем же соединением — будь то publish()
    из обработчика или heartbeat из другого потока — ломает AMQP-протокол
    и может привести к зависанию или разрыву соединения. Разделение по
    ролям делает паттерн «publish из обработчика» безопасным по построению.
    """

    def __init__(self, config: RabbitMQConfig) -> None:
        self.config: RabbitMQConfig = config
        self._parameters: ConnectionParameters = ConnectionParameters(
            host=config.host,
            port=config.port,
            virtual_host=config.virtual_host,
            credentials=PlainCredentials(
                username=config.user,
                password=config.password,
            ),
            heartbeat=config.heartbeat,
            blocked_connection_timeout=config.blocked_connection_timeout,
        )
        self._local: threading.local = threading.local()

    def _get_or_create_connection(self, attr: str, source: str, message: str) -> BlockingConnection:
        if not hasattr(self._local, attr) or not getattr(self._local, attr).is_open:
            logger.debug(
                {
                    'source': source,
                    'message': message,
                    'data': {'host': self._parameters.host, 'port': self._parameters.port},
                }
            )
            setattr(self._local, attr, BlockingConnection(parameters=self._parameters))
        return getattr(self._local, attr)

    def get_producer_connection(self) -> BlockingConnection:
        return self._get_or_create_connection(
            attr='producer_connection',
            source='RabbitMQConnectionManager.get_producer_connection',
            message='Creating new producer connection',
        )

    def get_consumer_connection(self) -> BlockingConnection:
        return self._get_or_create_connection(
            attr='consumer_connection',
            source='RabbitMQConnectionManager.get_consumer_connection',
            message='Creating new consumer connection',
        )

    def get_producer_channel(self) -> BlockingChannel:
        source: str = 'RabbitMQConnectionManager.get_producer_channel'
        connection: BlockingConnection = self.get_producer_connection()
        if not hasattr(self._local, 'producer_channel') or not self._local.producer_channel.is_open:
            logger.debug(
                {
                    'source': source,
                    'message': 'Creating new producer channel',
                    'data': {},
                }
            )
            channel: BlockingChannel = connection.channel()
            # Publisher confirms — basic_publish выбрасывает UnroutableError /
            # NackError вместо тихой потери сообщения, если брокер не может
            # его принять.
            channel.confirm_delivery()
            self._local.producer_channel = channel
        return self._local.producer_channel

    def reset_producer_channel(self) -> None:
        """
        Сбрасывает кешированный producer-канал и соединение. Вызывать после
        неудачной публикации, чтобы следующая публикация переподключилась.
        """
        source: str = 'RabbitMQConnectionManager.reset_producer_channel'
        logger.debug({'source': source, 'message': 'Resetting producer channel/connection', 'data': {}})

        channel: Optional[BlockingChannel] = getattr(self._local, 'producer_channel', None)
        if channel is not None:
            try:
                if channel.is_open:
                    channel.close()
            except (AMQPError, OSError) as exc:
                logger.warning(
                    {
                        'source': source,
                        'message': 'Failed to close producer channel',
                        'data': {'error': str(exc)},
                    }
                )
            delattr(self._local, 'producer_channel')

        connection: Optional[BlockingConnection] = getattr(self._local, 'producer_connection', None)
        if connection is not None:
            try:
                if connection.is_open:
                    connection.close()
            except (AMQPError, OSError) as exc:
                logger.warning(
                    {
                        'source': source,
                        'message': 'Failed to close producer connection',
                        'data': {'error': str(exc)},
                    }
                )
            delattr(self._local, 'producer_connection')
