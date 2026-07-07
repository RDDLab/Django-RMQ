import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from pika.exceptions import AMQPConnectionError
from pytest_mock import MockerFixture

import django_rmq
from django_rmq.consumer import Consumer
from django_rmq.registries.registry import get_consumers_registry
from django_rmq.registries.setup_registry import get_setup_registry
from tests.conftest import DEFAULT_ALIAS_PARAMS, SECOND_ALIAS_PARAMS

SETUP_COMMAND: str = 'setup_rabbitmq_topology'
START_COMMAND: str = 'start_consumers'
CHECK_COMMAND: str = 'check_rabbitmq_connections'


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


class CheckManagers:
    """
    Test double factory for `check_rabbitmq_connections.get_connection_manager`.

    Each alias resolves to a fresh mock manager. By default every alias is
    healthy — its `get_producer_connection` yields a mock connection. Call
    `fail(alias, exc)` to make that alias raise `exc` on connect instead.
    """

    def __init__(self) -> None:
        self._failures: dict[str, Exception] = {}
        self.connections: dict[str, MagicMock] = {}

    def fail(self, alias: str, exc: Exception) -> None:
        """
        Configures `alias` to raise `exc` when its connection is opened.
        """
        self._failures[alias] = exc

    def manager_for(self, using: str) -> MagicMock:
        """
        Builds the mock manager the command receives for `using`.
        """
        manager: MagicMock = MagicMock(name=f'ConnectionManager[{using}]')
        failure: Exception | None = self._failures.get(using)
        if failure is not None:
            manager.get_producer_connection.side_effect = failure
        else:
            connection: MagicMock = MagicMock(name=f'BlockingConnection[{using}]')
            connection.is_open = True
            manager.get_producer_connection.return_value = connection
            self.connections[using] = connection
        return manager


@pytest.fixture
def patch_check_managers(mocker: MockerFixture) -> CheckManagers:
    """
    Patches `get_connection_manager` in the check command with `CheckManagers`.
    """
    managers: CheckManagers = CheckManagers()
    mocker.patch(
        f'django_rmq.management.commands.{CHECK_COMMAND}.get_connection_manager',
        side_effect=lambda using: managers.manager_for(using=using),
    )
    return managers


class TestCheckConnectionsCommand:
    def test_all_aliases_ok_prints_ok_and_closes(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        call_command(CHECK_COMMAND)

        out: str = capsys.readouterr().out
        assert 'OK: default' in out
        assert 'ok: default' in out
        # A healthcheck must not leak the connection it opened.
        patch_check_managers.connections['default'].close.assert_called_once()

    def test_using_scopes_to_single_alias(
        self,
        patch_check_managers: CheckManagers,
        configure_rmq: Callable[[dict[str, dict[str, Any]]], None],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        configure_rmq({'default': DEFAULT_ALIAS_PARAMS, 'analytics': SECOND_ALIAS_PARAMS})

        call_command(CHECK_COMMAND, using='analytics')

        out: str = capsys.readouterr().out
        assert 'OK: analytics' in out
        # The unselected alias is never touched.
        assert 'default' not in patch_check_managers.connections
        assert 'analytics' in patch_check_managers.connections

    def test_failed_alias_raises_command_error(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        patch_check_managers.fail(alias='default', exc=AMQPConnectionError('boom'))

        with pytest.raises(CommandError, match='default'):
            call_command(CHECK_COMMAND)

        assert 'FAIL: default' in capsys.readouterr().err

    def test_partial_failure_reports_only_failed(
        self,
        patch_check_managers: CheckManagers,
        configure_rmq: Callable[[dict[str, dict[str, Any]]], None],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        configure_rmq({'default': DEFAULT_ALIAS_PARAMS, 'analytics': SECOND_ALIAS_PARAMS})
        patch_check_managers.fail(alias='analytics', exc=AMQPConnectionError('boom'))

        with pytest.raises(CommandError) as exc_info:
            call_command(CHECK_COMMAND)

        message: str = str(exc_info.value)
        assert 'analytics' in message
        assert 'default' not in message
        captured: pytest.CaptureFixture[str] = capsys.readouterr()
        assert 'OK: default' in captured.out
        assert 'FAIL: analytics' in captured.err

    def test_oserror_is_caught(self, patch_check_managers: CheckManagers) -> None:
        # Connection refused surfaces as OSError, not AMQPError — both must be caught.
        patch_check_managers.fail(alias='default', exc=OSError('connection refused'))

        with pytest.raises(CommandError, match='default'):
            call_command(CHECK_COMMAND)

    def test_not_initialized_raises_improperly_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # reset_rmq_state (autouse) rebuilds the managers after the test.
        monkeypatch.setattr(django_rmq, 'connection_managers', None)

        with pytest.raises(ImproperlyConfigured):
            call_command(CHECK_COMMAND)

    def test_warning_logged_on_failure(
        self, patch_check_managers: CheckManagers, caplog: pytest.LogCaptureFixture
    ) -> None:
        patch_check_managers.fail(alias='default', exc=AMQPConnectionError('boom'))

        with caplog.at_level(logging.WARNING, logger='rabbitmq'), pytest.raises(CommandError):
            call_command(CHECK_COMMAND)

        record: logging.LogRecord = next(r for r in caplog.records if r.levelno == logging.WARNING)
        payload: Any = record.msg
        assert payload['source'] == CHECK_COMMAND
        assert payload['message'] == 'RabbitMQ connection failed'
        assert payload['data']['alias'] == 'default'
        assert 'boom' in payload['data']['error']
