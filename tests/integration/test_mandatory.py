import pytest
from pika.exceptions import ChannelClosedByBroker, UnroutableError

from django_rmq.producer import Producer
from tests.integration.conftest import Names

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
