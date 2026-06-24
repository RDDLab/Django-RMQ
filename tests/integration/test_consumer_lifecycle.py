import threading
from typing import Any

import pytest
from pika.adapters.blocking_connection import BlockingChannel

from django_rmq.consumer import Consumer
from django_rmq.producer import Producer
from tests.integration.conftest import MgmtApi, Names, poll

pytestmark = pytest.mark.integration


class TestConsumerLifecycle:
    """
    Consumer lifecycle and multi-alias behaviour against a real broker: graceful
    stop, prefetch limits, vhost isolation between aliases.
    """

    def test_graceful_stop_exits_promptly(
        self,
        configure_real_rmq,
        admin_channel: BlockingChannel,
        names: Names,
        run_consumer,
    ):
        configure_real_rmq()
        admin_channel.queue_declare(queue=names.queue, durable=True)

        consumer: Consumer = Consumer(queue=names.queue)
        consumer.handler(func=lambda ch, method, props, body: None)

        running = run_consumer(consumer)
        # Let the consume loop actually start before requesting shutdown.
        assert poll(lambda: running.thread.is_alive())

        running.stop_event.set()
        running.thread.join(timeout=5)
        assert not running.thread.is_alive(), 'consumer did not stop within the interval'

    def test_prefetch_limits_unacked_messages(
        self,
        configure_real_rmq,
        admin_channel: BlockingChannel,
        names: Names,
        run_consumer,
        mgmt_api: MgmtApi,
    ):
        configure_real_rmq()
        admin_channel.queue_declare(queue=names.queue, durable=True)

        gate: threading.Event = threading.Event()
        acked: list[bytes] = []
        consumer: Consumer = Consumer(queue=names.queue, prefetch_count=1)

        @consumer
        def handler(ch: BlockingChannel, method: Any, props: Any, body: bytes) -> None:
            gate.wait(timeout=10)  # hold the delivery unacked until the test releases it
            ch.basic_ack(delivery_tag=method.delivery_tag)
            acked.append(body)

        producer: Producer = Producer(queue=names.queue)
        producer.publish(body=b'm1')
        producer.publish(body=b'm2')

        run_consumer(consumer)

        # prefetch_count=1: exactly one delivery in flight, the other still ready.
        assert poll(lambda: mgmt_api.messages_unacknowledged(names.queue) == 1)
        assert mgmt_api.messages(names.queue) == 1

        gate.set()
        assert poll(lambda: len(acked) == 2, timeout=10)
        assert poll(lambda: mgmt_api.messages(names.queue) == 0)

    def test_multi_alias_vhost_isolation(
        self,
        configure_real_rmq,
        admin_channel: BlockingChannel,
        broker_params: dict[str, Any],
        names: Names,
        mgmt_api: MgmtApi,
    ):
        # Second alias = same broker, a throwaway vhost created just for this test.
        second_vhost: str = f'django-rmq-test-{names.suffix}'
        mgmt_api.create_vhost(name=second_vhost, user=broker_params['USER'])
        try:
            params_b: dict[str, Any] = {**broker_params, 'VIRTUAL_HOST': second_vhost}
            configure_real_rmq({'a': dict(broker_params), 'b': params_b})

            # The queue exists only in alias 'a' (admin_channel lives in vhost 'a').
            admin_channel.queue_declare(queue=names.queue, durable=True)
            Producer(queue=names.queue, using='a').publish(body=b'only-in-a')

            assert poll(lambda: mgmt_api.messages(names.queue) == 1)
            # The same queue name must not exist in alias 'b''s vhost.
            assert mgmt_api.for_vhost(vhost=second_vhost).queue(name=names.queue) is None
        finally:
            mgmt_api.delete_vhost(name=second_vhost)
