from typing import cast
from unittest.mock import MagicMock

import pytest
from pika.exceptions import AMQPError
from pytest_mock import MockerFixture

from django_rmq.connections import RabbitMQConnectionManager
from django_rmq.dto.rabbitmq_config import RabbitMQConfig


def _make_config() -> RabbitMQConfig:
    return RabbitMQConfig(
        host='localhost',
        port=5672,
        virtual_host='/',
        user='guest',
        password='guest',
        heartbeat=600,
        blocked_connection_timeout=300,
        reconnect_initial_backoff=1.0,
        reconnect_max_backoff=30.0,
    )


@pytest.fixture
def distinct_connections(mocker: MockerFixture) -> list[MagicMock]:
    """
    Patches `BlockingConnection` to return a fresh mock connection per call.

    Each connection yields a fresh mock channel per `.channel()` call, so tests
    can distinguish separate connections/channels by identity. The returned list
    accumulates every connection created, in order.
    """
    created: list[MagicMock] = []

    def factory(**_kwargs: object) -> MagicMock:
        connection = MagicMock(name=f'connection-{len(created)}')
        connection.is_open = True
        connection.channel.side_effect = lambda: _make_channel()
        created.append(connection)
        return connection

    def _make_channel() -> MagicMock:
        channel = MagicMock(name='channel')
        channel.is_open = True
        return channel

    mocker.patch('django_rmq.connections.BlockingConnection', side_effect=factory)
    return created


class TestConnectionRoles:
    def test_producer_and_consumer_connections_are_separate(self, distinct_connections: list[MagicMock]) -> None:
        manager = RabbitMQConnectionManager(config=_make_config())
        producer_connection = manager.get_producer_connection()
        consumer_connection = manager.get_consumer_connection()

        assert producer_connection is not consumer_connection
        assert len(distinct_connections) == 2

    def test_producer_connection_is_reused(self, distinct_connections: list[MagicMock]) -> None:
        manager = RabbitMQConnectionManager(config=_make_config())
        first = manager.get_producer_connection()
        second = manager.get_producer_connection()

        assert first is second
        assert len(distinct_connections) == 1


class TestProducerChannel:
    def test_channel_enables_confirms_and_is_reused(self, distinct_connections: list[MagicMock]) -> None:
        manager = RabbitMQConnectionManager(config=_make_config())
        channel = cast(MagicMock, manager.get_producer_channel())
        again = manager.get_producer_channel()

        assert channel is again
        channel.confirm_delivery.assert_called_once()
        distinct_connections[0].channel.assert_called_once()

    def test_closed_channel_is_recreated(self, distinct_connections: list[MagicMock]) -> None:
        manager = RabbitMQConnectionManager(config=_make_config())
        channel = cast(MagicMock, manager.get_producer_channel())
        channel.is_open = False

        new_channel = manager.get_producer_channel()

        assert new_channel is not channel
        assert distinct_connections[0].channel.call_count == 2


class TestResetProducerChannel:
    def test_reset_closes_channel_and_connection(self, distinct_connections: list[MagicMock]) -> None:
        manager = RabbitMQConnectionManager(config=_make_config())
        channel = cast(MagicMock, manager.get_producer_channel())
        connection = distinct_connections[0]

        manager.reset_producer_channel()

        channel.close.assert_called_once()
        connection.close.assert_called_once()
        # The next access opens a brand-new connection.
        manager.get_producer_channel()
        assert len(distinct_connections) == 2

    def test_reset_swallows_close_errors(self, distinct_connections: list[MagicMock]) -> None:
        manager = RabbitMQConnectionManager(config=_make_config())
        channel = cast(MagicMock, manager.get_producer_channel())
        channel.close.side_effect = AMQPError('cannot close')

        # Must not raise despite the failing close.
        manager.reset_producer_channel()

        # State was still cleared — the next access opens a new connection.
        manager.get_producer_channel()
        assert len(distinct_connections) == 2

    def test_reset_without_existing_channel_is_noop(self, distinct_connections: list[MagicMock]) -> None:
        manager = RabbitMQConnectionManager(config=_make_config())
        # Nothing opened yet — reset should be harmless.
        manager.reset_producer_channel()
        assert distinct_connections == []
