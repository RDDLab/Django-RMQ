from unittest.mock import MagicMock

import pytest
from pika import DeliveryMode
from pika.exceptions import AMQPConnectionError
from pika.spec import BasicProperties
from pytest_mock import MockerFixture

from django_rmq.producer import Producer
from django_rmq.queues.queue_config import QueueConfig, QueueType


@pytest.fixture
def mock_manager(mocker: MockerFixture, mock_channel: MagicMock) -> MagicMock:
    """
    Patches `get_connection_manager` in the producer module.

    The returned manager hands out `mock_channel` from `get_producer_channel`,
    so publish paths run entirely against the mock channel.
    """
    manager = MagicMock(name='ConnectionManager')
    manager.get_producer_channel.return_value = mock_channel
    mocker.patch('django_rmq.producer.get_connection_manager', return_value=manager)
    return manager


class TestProducerPublishBody:
    def test_str_body_is_encoded_to_bytes(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        Producer(queue='orders').publish(body='hello')
        assert mock_channel.basic_publish.call_args.kwargs['body'] == b'hello'

    def test_bytes_body_is_passed_through(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        Producer(queue='orders').publish(body=b'raw')
        assert mock_channel.basic_publish.call_args.kwargs['body'] == b'raw'

    def test_publish_is_always_mandatory(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        Producer(queue='orders').publish(body='x')
        assert mock_channel.basic_publish.call_args.kwargs['mandatory'] is True


class TestProducerProperties:
    def test_default_properties_are_persistent_json(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        Producer(queue='orders').publish(body='x')
        props: BasicProperties = mock_channel.basic_publish.call_args.kwargs['properties']
        assert props.delivery_mode == DeliveryMode.Persistent.value
        assert props.content_type == 'application/json'

    def test_custom_properties_without_delivery_mode_are_forced_persistent(
        self, mock_manager: MagicMock, mock_channel: MagicMock
    ) -> None:
        Producer(queue='orders').publish(body='x', properties=BasicProperties(content_type='text/plain'))
        props: BasicProperties = mock_channel.basic_publish.call_args.kwargs['properties']
        assert props.delivery_mode == DeliveryMode.Persistent.value
        assert props.content_type == 'text/plain'

    def test_custom_delivery_mode_is_respected(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        Producer(queue='orders').publish(
            body='x',
            properties=BasicProperties(delivery_mode=DeliveryMode.Transient.value),
        )
        props: BasicProperties = mock_channel.basic_publish.call_args.kwargs['properties']
        assert props.delivery_mode == DeliveryMode.Transient.value


class TestProducerRoutingKey:
    def test_routing_key_defaults_to_queue_name(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        Producer(queue='orders').publish(body='x')
        assert mock_channel.basic_publish.call_args.kwargs['routing_key'] == 'orders'

    def test_explicit_routing_key_overrides_queue(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        Producer(exchange='events', queue='orders').publish(body='x', routing_key='payments.created')
        assert mock_channel.basic_publish.call_args.kwargs['routing_key'] == 'payments.created'

    def test_exchange_is_passed_through(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        Producer(exchange='events', queue='').publish(body='x', routing_key='rk')
        assert mock_channel.basic_publish.call_args.kwargs['exchange'] == 'events'


class TestProducerQueueDeclaration:
    def test_string_queue_declared_passively(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        Producer(queue='orders').publish(body='x')
        mock_channel.queue_declare.assert_called_once_with(queue='orders', passive=True)

    def test_queue_config_declared_actively_with_arguments(
        self, mock_manager: MagicMock, mock_channel: MagicMock
    ) -> None:
        config = QueueConfig(
            name='orders',
            dead_letter_exchange='dlx-orders',
            dead_letter_routing_key='dlq-orders',
        )
        Producer(queue=config).publish(body='x')
        mock_channel.queue_declare.assert_called_once_with(
            queue='orders',
            durable=True,
            arguments={
                'x-dead-letter-exchange': 'dlx-orders',
                'x-dead-letter-routing-key': 'dlq-orders',
            },
        )

    def test_queue_config_with_queue_type_declared_actively(
        self, mock_manager: MagicMock, mock_channel: MagicMock
    ) -> None:
        config = QueueConfig(name='orders', queue_type=QueueType.QUORUM)
        Producer(queue=config).publish(body='x')
        mock_channel.queue_declare.assert_called_once_with(
            queue='orders',
            durable=True,
            arguments={'x-queue-type': 'quorum'},
        )

    def test_empty_queue_skips_declaration(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        Producer(exchange='events', queue='').publish(body='x', routing_key='rk')
        mock_channel.queue_declare.assert_not_called()

    def test_queue_declared_only_once_across_publishes(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        producer = Producer(queue='orders')
        producer.publish(body='one')
        producer.publish(body='two')
        mock_channel.queue_declare.assert_called_once()


class TestProducerRetry:
    def test_reconnectable_error_resets_and_retries_once(
        self, mock_manager: MagicMock, mock_channel: MagicMock
    ) -> None:
        # First attempt fails on a dead channel; the retry succeeds.
        mock_channel.basic_publish.side_effect = [AMQPConnectionError('dead'), None]
        Producer(queue='orders').publish(body='x')
        assert mock_channel.basic_publish.call_count == 2
        mock_manager.reset_producer_channel.assert_called_once()

    def test_retry_also_failing_propagates(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        mock_channel.basic_publish.side_effect = AMQPConnectionError('still dead')
        with pytest.raises(AMQPConnectionError):
            Producer(queue='orders').publish(body='x')
        assert mock_channel.basic_publish.call_count == 2
        mock_manager.reset_producer_channel.assert_called_once()

    def test_non_reconnectable_error_is_not_retried(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        mock_channel.basic_publish.side_effect = ValueError('boom')
        with pytest.raises(ValueError):
            Producer(queue='orders').publish(body='x')
        assert mock_channel.basic_publish.call_count == 1
        mock_manager.reset_producer_channel.assert_not_called()


class TestProducerDecorator:
    def test_str_return_value_is_published(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        producer = Producer(queue='notifications')

        @producer
        def build() -> str:
            return 'payload'

        result = build()
        assert result == 'payload'
        assert mock_channel.basic_publish.call_args.kwargs['body'] == b'payload'

    def test_bytes_return_value_is_published(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        producer = Producer(queue='notifications')

        @producer
        def build() -> bytes:
            return b'payload'

        build()
        assert mock_channel.basic_publish.call_args.kwargs['body'] == b'payload'

    def test_none_return_value_skips_publish(self, mock_manager: MagicMock, mock_channel: MagicMock) -> None:
        producer = Producer(queue='notifications')

        @producer
        def build() -> None:
            return None

        assert build() is None
        mock_channel.basic_publish.assert_not_called()

    def test_non_str_bytes_return_raises_type_error(self, mock_manager: MagicMock) -> None:
        producer = Producer(queue='notifications')

        @producer
        def build() -> int:  # type: ignore[return-value]
            return 42  # type: ignore[return-value]

        with pytest.raises(TypeError, match='must return str'):
            build()
