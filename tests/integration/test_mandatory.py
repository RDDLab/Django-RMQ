from typing import Any

import pytest
from pika.exceptions import ChannelClosedByBroker, UnroutableError

from django_rmq.producer import Producer
from tests.integration.conftest import MgmtApi, Names, poll

pytestmark = pytest.mark.integration


class TestMandatory:
    """
    Publisher-confirms + `mandatory=True` behaviour against a real broker.

    The unit suite proves we pass `mandatory=True`; only a live broker can prove the
    *consequences*: an unroutable message raises `UnroutableError`, and a passive
    declare of a missing queue raises `ChannelClosedByBroker`.
    """

    def test_mandatory_unroutable_raises(self, configure_real_rmq, admin_channel, names: Names):
        # admin_channel is unused for setup but drives name cleanup on teardown.
        configure_real_rmq()
        # Exchange-only producer publishing to the default exchange with a routing
        # key that matches no queue -> broker returns the message -> UnroutableError.
        producer: Producer = Producer(exchange='', queue='')

        with pytest.raises(UnroutableError):
            producer.publish(body=b'nowhere', routing_key=names.queue)

    def test_passive_declare_of_missing_queue_raises(self, configure_real_rmq, admin_channel, names: Names):
        configure_real_rmq()
        # A string queue triggers queue_declare(passive=True); the queue does not
        # exist, so the broker closes the channel with 404. ChannelClosedByBroker is
        # reconnectable, so publish() retries once and then propagates it.
        producer: Producer = Producer(queue=names.queue)

        with pytest.raises(ChannelClosedByBroker):
            producer.publish(body=b'no-such-queue')

    def test_passive_declare_with_write_only_permission(
        self,
        write_only_user_params: dict[str, Any],
        configure_real_rmq,
        admin_channel,
        mgmt_api: MgmtApi,
        names: Names,
    ):
        # write_only_user_params comes first so the user outlives (is torn down
        # after) the producer connection that configure_real_rmq closes.
        # A pure producer typically holds only the `write` permission. Its passive
        # queue_declare must still succeed: RabbitMQ 4.2.6 and 4.3.0 required
        # `configure` for it (rabbitmq-server#16085), 4.2.7+/4.3.1+/4.4 accept any
        # of configure/write/read (#16272). Guards against that regression.
        admin_channel.queue_declare(queue=names.queue, durable=True)
        configure_real_rmq(connections={'default': write_only_user_params})
        producer: Producer = Producer(queue=names.queue)

        producer.publish(body=b'write-only')

        assert poll(predicate=lambda: mgmt_api.messages(name=names.queue) == 1)
