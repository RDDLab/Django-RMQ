import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from pytest_mock import MockerFixture

from django_rmq.consumer import Consumer
from django_rmq.registries.registry import get_consumers_registry
from django_rmq.registries.setup_registry import get_setup_registry
from tests.conftest import DEFAULT_ALIAS_PARAMS, SECOND_ALIAS_PARAMS

SETUP_COMMAND: str = 'setup_rabbitmq_topology'
START_COMMAND: str = 'start_consumers'


@pytest.fixture
def patch_setup_manager(mocker: MockerFixture, mock_connection: MagicMock) -> MagicMock:
    """
    Patches `get_connection_manager` in the setup command to a mock manager whose
    producer connection yields the mocked channel.
    """
    manager = MagicMock(name='ConnectionManager')
    manager.get_producer_connection.return_value = mock_connection
    mocker.patch(f'django_rmq.management.commands.{SETUP_COMMAND}.get_connection_manager', return_value=manager)
    return manager


class TestSetupCommand:
    def test_runs_setup_functions_and_reports_topology(
        self, patch_setup_manager: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def setup_orders(channel: Any) -> None:
            channel.exchange_declare(exchange='dlx-orders', exchange_type='direct', durable=True)
            channel.queue_declare(queue='orders', durable=True)
            channel.queue_bind(queue='orders', exchange='dlx-orders', routing_key='orders')

        get_setup_registry().register(fn=setup_orders)

        call_command(SETUP_COMMAND)

        out = capsys.readouterr().out
        assert 'RabbitMQ setup complete' in out
        assert 'dlx-orders' in out
        assert 'orders' in out

    def test_using_scopes_to_single_alias(
        self,
        patch_setup_manager: MagicMock,
        configure_rmq: Callable[[dict[str, dict[str, Any]]], None],
    ) -> None:
        configure_rmq({'default': DEFAULT_ALIAS_PARAMS, 'analytics': SECOND_ALIAS_PARAMS})
        ran: list[str] = []
        get_setup_registry(using='default').register(fn=lambda channel: ran.append('default'))
        get_setup_registry(using='analytics').register(fn=lambda channel: ran.append('analytics'))

        call_command(SETUP_COMMAND, using='analytics')

        assert ran == ['analytics']


class TestStartConsumersCommand:
    def test_spawns_thread_per_consumer(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        # Patch consume so the spawned threads return immediately.
        consume = mocker.patch.object(Consumer, 'consume', return_value=None)
        consumer = Consumer(queue='orders')
        consumer.handler(func=lambda ch, method, props, body: None)
        get_consumers_registry().register(consumer=consumer)

        call_command(START_COMMAND)

        out = capsys.readouterr().out
        assert 'queue=orders' in out
        consume.assert_called_once()

    def test_no_consumers_warns_and_returns(
        self, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with caplog.at_level(logging.WARNING, logger='rabbitmq'):
            call_command(START_COMMAND)

        assert 'No consumers registered' in caplog.text
        # The consumer table is never rendered when there is nothing to start.
        assert 'queue=' not in capsys.readouterr().out
