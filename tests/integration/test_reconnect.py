import threading
from typing import Any

import pytest
from pika.adapters.blocking_connection import BlockingChannel

from django_rmq.consumer import Consumer
from django_rmq.producer import Producer
from tests.integration.conftest import MgmtApi, Names, poll

pytestmark = pytest.mark.integration


class TestReconnect:
    """
    Reconnect / self-heal tests driven by force-closing connections through the
    Management API. They exercise the consumer's reconnect-with-backoff loop and the
    producer's "drop the dead channel and republish" path against a real broker,
    without restarting the broker process.
    """

    def _new_connection_name(self, mgmt_api: MgmtApi, known: set[str]) -> str | None:
        """
        Returns the name of a connection that appeared since `known` was snapshotted.
        """
        current: list[dict[str, Any]] = mgmt_api.list_connections()
        fresh: set[str] = {c['name'] for c in current} - known
        return next(iter(fresh), None)

    def test_consumer_reconnects_after_connection_kill(
        self,
        configure_real_rmq,
        admin_channel: BlockingChannel,
        names: Names,
        run_consumer,
        mgmt_api: MgmtApi,
    ):
        configure_real_rmq()
        admin_channel.queue_declare(queue=names.queue, durable=True)

        received: list[bytes] = []
        done: threading.Event = threading.Event()
        consumer: Consumer = Consumer(queue=names.queue)

        @consumer
        def handler(ch: BlockingChannel, method: Any, props: Any, body: bytes) -> None:
            received.append(body)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            done.set()

        before: set[str] = {c['name'] for c in mgmt_api.list_connections()}
        run_consumer(consumer)

        # Wait for the consumer's connection, then force-close it broker-side.
        consumer_connection: str | None = poll(lambda: self._new_connection_name(mgmt_api=mgmt_api, known=before))
        assert consumer_connection, 'consumer connection never appeared'
        mgmt_api.kill_connection(name=consumer_connection)

        # The consumer must reconnect on its own and deliver a message published
        # after the disconnect (the durable queue holds it until then).
        Producer(queue=names.queue).publish(body=b'after-reconnect')

        assert done.wait(timeout=10), 'consumer did not recover after connection kill'
        assert received == [b'after-reconnect']

    def test_producer_recovers_after_connection_kill(
        self,
        configure_real_rmq,
        admin_channel: BlockingChannel,
        names: Names,
        mgmt_api: MgmtApi,
    ):
        configure_real_rmq()
        admin_channel.queue_declare(queue=names.queue, durable=True)
        producer: Producer = Producer(queue=names.queue)

        before: set[str] = {c['name'] for c in mgmt_api.list_connections()}
        producer.publish(body=b'first')  # opens the producer connection/channel

        producer_connection: str | None = poll(lambda: self._new_connection_name(mgmt_api=mgmt_api, known=before))
        assert producer_connection, 'producer connection never appeared'
        mgmt_api.kill_connection(name=producer_connection)

        # Next publish must transparently reconnect (dead channel -> reset + retry,
        # or self-heal via the is_open check) and land the second message. (The
        # Management connection list is eventually consistent, so we assert on the
        # end state — both messages present — rather than on the kill being visible.)
        producer.publish(body=b'second')

        assert poll(lambda: mgmt_api.messages(names.queue) == 2), 'producer did not recover after connection kill'
