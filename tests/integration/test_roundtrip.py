import threading
from collections.abc import Callable
from typing import Any

import pytest
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType

from django_rmq.consumer import Consumer
from django_rmq.producer import Producer
from tests.integration.conftest import Names

pytestmark = pytest.mark.integration


class TestRoundtrip:
    """
    Round-trip integration tests: a real Producer publishes, a real Consumer
    receives. These prove the end-to-end AMQP path that the mocked unit tests
    cannot — actual routing through the default and direct exchanges.
    """

    def _capture_handler(self, received: list[bytes], done: threading.Event) -> Callable:
        """
        Builds a handler that records the body, acknowledges (`ack`), and signals `done`.
        """

        def handler(ch: BlockingChannel, method: Any, props: Any, body: bytes) -> None:
            received.append(body)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            done.set()

        return handler

    def test_roundtrip_default_exchange(
        self,
        configure_real_rmq,
        admin_channel: BlockingChannel,
        names: Names,
        run_consumer,
    ):
        configure_real_rmq()
        admin_channel.queue_declare(queue=names.queue, durable=True)

        received: list[bytes] = []
        done: threading.Event = threading.Event()
        consumer: Consumer = Consumer(queue=names.queue)
        consumer.handler(func=self._capture_handler(received=received, done=done))
        run_consumer(consumer)

        Producer(queue=names.queue).publish(body='{"order_id": 42}')

        assert done.wait(timeout=10), 'consumer never received the message'
        assert received == [b'{"order_id": 42}']

    def test_roundtrip_direct_exchange_routing_key(
        self,
        configure_real_rmq,
        admin_channel: BlockingChannel,
        names: Names,
        run_consumer,
    ):
        configure_real_rmq()
        routing_key: str = 'payments.created'
        admin_channel.exchange_declare(exchange=names.exchange, exchange_type=ExchangeType.direct, durable=True)
        admin_channel.queue_declare(queue=names.queue, durable=True)
        admin_channel.queue_bind(queue=names.queue, exchange=names.exchange, routing_key=routing_key)

        received: list[bytes] = []
        done: threading.Event = threading.Event()
        consumer: Consumer = Consumer(queue=names.queue)
        consumer.handler(func=self._capture_handler(received=received, done=done))
        run_consumer(consumer)

        Producer(exchange=names.exchange, queue='').publish(body=b'raw bytes payload', routing_key=routing_key)

        assert done.wait(timeout=10)
        assert received == [b'raw bytes payload']
