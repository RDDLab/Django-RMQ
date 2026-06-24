import threading
from typing import Any

import pytest
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType

from django_rmq.consumer import Consumer
from django_rmq.producer import Producer
from django_rmq.queues.queue_config import QueueConfig
from tests.integration.conftest import MgmtApi, Names, poll

pytestmark = pytest.mark.integration


class TestDeadLetter:
    """
    Dead-letter integration tests. The unit suite proves `_dispatch` *calls*
    `basic_nack(requeue=False)`; here we prove the broker actually routes the
    nacked message to the configured dead-letter exchange and into the DLQ.
    """

    def _declare_dlx_topology(self, admin_channel: BlockingChannel, names: Names) -> QueueConfig:
        """
        Declares the DLX + DLQ and returns a QueueConfig wiring the main queue to them.
        """
        admin_channel.exchange_declare(exchange=names.dlx, exchange_type=ExchangeType.direct, durable=True)
        admin_channel.queue_declare(queue=names.dlq, durable=True)
        admin_channel.queue_bind(queue=names.dlq, exchange=names.dlx, routing_key=names.dlq)
        return QueueConfig(
            name=names.queue,
            dead_letter_exchange=names.dlx,
            dead_letter_routing_key=names.dlq,
        )

    def test_handler_exception_dead_letters_to_dlq(
        self,
        configure_real_rmq,
        admin_channel: BlockingChannel,
        names: Names,
        run_consumer,
        mgmt_api: MgmtApi,
    ):
        queue_config: QueueConfig = self._declare_dlx_topology(admin_channel=admin_channel, names=names)
        configure_real_rmq()

        seen: threading.Event = threading.Event()
        consumer: Consumer = Consumer(queue=queue_config)

        @consumer
        def handler(ch: BlockingChannel, method: Any, props: Any, body: bytes) -> None:
            seen.set()
            raise ValueError('boom')  # dispatcher nacks without requeue -> DLX

        run_consumer(consumer)
        Producer(queue=queue_config).publish(body='{"will": "fail"}')

        assert seen.wait(timeout=10)
        assert poll(lambda: mgmt_api.messages(names.dlq) == 1), 'message did not reach the DLQ'
        # And it left the main queue (neither ready nor unacked there).
        assert poll(lambda: mgmt_api.messages(names.queue) == 0)
