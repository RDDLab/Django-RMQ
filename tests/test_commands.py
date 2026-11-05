import io
import json
import logging
import re
import threading
import time
from collections.abc import Callable, Iterator
from types import SimpleNamespace
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
from django_rmq.dto.healthcheck_config import HealthcheckConfig
from django_rmq.management.commands.check_rabbitmq_connections import Command
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
    Test double for the node probes of `check_rabbitmq_connections`.

    Each alias resolves to a mock manager whose `build_probe_parameters` yields
    one parameters object per node; by default an alias has a single healthy
    node `<alias>-node-2:5672`. `Command._probe_node` is patched to look up the
    configured behavior of the probed host: succeed, raise, or hang until the
    test ends.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, list[str]] = {}
        self._failures: dict[str, Exception] = {}
        self._hanging: set[str] = set()
        self.release: threading.Event = threading.Event()
        self.probed: list[str] = []
        self.probe_kwargs: dict[str, Any] = {}

    def set_nodes(self, alias: str, hosts: list[str]) -> None:
        """
        Configures the node hosts of `alias` (all on port 5672).
        """
        self._nodes[alias] = hosts

    def hosts_for(self, alias: str) -> list[str]:
        """
        Returns the node hosts of `alias`.
        """
        return self._nodes.get(alias, [f'{alias}-node-2'])

    def fail(self, alias: str, exc: Exception) -> None:
        """
        Configures every node of `alias` to raise `exc` when probed.
        """
        for host in self.hosts_for(alias=alias):
            self._failures[host] = exc

    def fail_node(self, host: str, exc: Exception) -> None:
        """
        Configures a single node to raise `exc` when probed.
        """
        self._failures[host] = exc

    def hang_node(self, host: str) -> None:
        """
        Configures a single node to never answer (until the test ends).
        """
        self._hanging.add(host)

    def manager_for(self, using: str) -> MagicMock:
        """
        Builds the mock manager the command receives for `using`.
        """
        manager: MagicMock = MagicMock(name=f'ConnectionManager[{using}]')

        def build_probe_parameters(**kwargs: Any) -> list[SimpleNamespace]:
            self.probe_kwargs = kwargs
            return [SimpleNamespace(host=host, port=5672) for host in self.hosts_for(alias=using)]

        manager.build_probe_parameters.side_effect = build_probe_parameters
        return manager

    def probe(self, params: SimpleNamespace) -> None:
        """
        Replacement for `Command._probe_node`.
        """
        self.probed.append(params.host)
        if params.host in self._hanging:
            self.release.wait(timeout=30)
        failure: Exception | None = self._failures.get(params.host)
        if failure is not None:
            raise failure


@pytest.fixture
def patch_check_managers(mocker: MockerFixture) -> Iterator[CheckManagers]:
    """
    Patches `get_connection_manager` and `Command._probe_node` in the check command.
    """
    managers: CheckManagers = CheckManagers()
    mocker.patch(
        f'django_rmq.management.commands.{CHECK_COMMAND}.get_connection_manager',
        side_effect=lambda using: managers.manager_for(using=using),
    )
    mocker.patch.object(Command, '_probe_node', side_effect=lambda params: managers.probe(params=params))
    yield managers
    managers.release.set()


def _json_lines(out: str) -> list[dict[str, Any]]:
    """
    Parses the command's JSON-lines output into a list of events.
    """
    return [json.loads(line) for line in out.splitlines() if line]


class TestCheckConnectionsCommand:
    def test_json_format_success(self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]) -> None:
        call_command(CHECK_COMMAND, output_format='json')

        events: list[dict[str, Any]] = _json_lines(out=capsys.readouterr().out)
        assert [event['event'] for event in events] == ['startup', 'check', 'summary']
        check: dict[str, Any] = events[1]
        assert check['status'] == 'ok'
        assert check['alias'] == 'default'
        assert check['node'] == 'default-node-2:5672'
        assert isinstance(check['seconds'], float)
        summary: dict[str, Any] = events[2]
        assert summary == {
            'event': 'summary',
            'status': 'healthy',
            'healthy': 1,
            'total': 1,
            'failed': [],
            'seconds': summary['seconds'],
        }
        assert patch_check_managers.probed == ['default-node-2']

    def test_default_format_is_text(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        call_command(CHECK_COMMAND)

        lines: list[str] = capsys.readouterr().out.splitlines()
        assert len(lines) == 3
        assert re.fullmatch(r'startup=(\d+\.\d{2}s|unknown)', lines[0])
        assert re.fullmatch(r'OK alias=default node=default-node-2:5672 connect=\d+\.\d{2}s', lines[1])
        assert re.fullmatch(r'HEALTHY aliases=1/1 total=\d+\.\d{2}s', lines[2])

    def test_text_format_failure_quotes_error(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        patch_check_managers.fail(alias='default', exc=OSError('connection "refused"'))

        with pytest.raises(CommandError, match='default'):
            call_command(CHECK_COMMAND, output_format='text')

        lines: list[str] = capsys.readouterr().out.splitlines()
        assert len(lines) == 4
        assert re.fullmatch(r'FAIL alias=default took=\d+\.\d{2}s', lines[1])
        assert re.fullmatch(r'UNHEALTHY failed=default aliases=0/1 total=\d+\.\d{2}s', lines[2])
        assert lines[3] == 'ERROR alias=default error="default-node-2:5672 OSError: connection \\"refused\\""'

    def test_text_format_short_lines_and_summary_precede_errors(
        self,
        patch_check_managers: CheckManagers,
        configure_rmq: Callable[[dict[str, dict[str, Any]]], None],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        configure_rmq({'default': DEFAULT_ALIAS_PARAMS, 'analytics': SECOND_ALIAS_PARAMS})
        patch_check_managers.fail(alias='default', exc=AMQPConnectionError('x' * 500))
        patch_check_managers.fail(alias='analytics', exc=OSError('refused'))

        with pytest.raises(CommandError):
            call_command(CHECK_COMMAND)

        lines: list[str] = capsys.readouterr().out.splitlines()
        assert lines[0].startswith('startup=')
        assert [line.split(' ', 1)[0] for line in lines[1:]] == ['FAIL', 'FAIL', 'UNHEALTHY', 'ERROR', 'ERROR']
        # Aliases are checked in parallel, so they are reported in completion order.
        summary_pattern: str = r'UNHEALTHY failed=(default,analytics|analytics,default) aliases=0/2 total=\d+\.\d{2}s'
        assert re.fullmatch(summary_pattern, lines[3])
        assert sorted(lines[4:]) == [
            'ERROR alias=analytics error="analytics-node-2:5672 OSError: refused"',
            f'ERROR alias=default error="default-node-2:5672 AMQPConnectionError: {"x" * 500}"',
        ]

    def test_output_is_never_colored(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        patch_check_managers.fail(alias='default', exc=AMQPConnectionError('boom'))

        with pytest.raises(CommandError):
            call_command(CHECK_COMMAND, output_format='text', force_color=True)

        captured: pytest.CaptureFixture[str] = capsys.readouterr()
        assert '\x1b[' not in captured.out
        assert '\x1b[' not in captured.err

    def test_empty_exception_message_falls_back_to_type_name(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        patch_check_managers.fail(alias='default', exc=AMQPConnectionError())

        with pytest.raises(CommandError):
            call_command(CHECK_COMMAND, output_format='json')

        check: dict[str, Any] = _json_lines(out=capsys.readouterr().out)[1]
        assert check['status'] == 'fail'
        assert check['error'] == 'default-node-2:5672 AMQPConnectionError'
        assert 'node' not in check

    def test_unknown_startup_is_reported(
        self, patch_check_managers: CheckManagers, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mocker.patch(
            f'django_rmq.management.commands.{CHECK_COMMAND}.Command._get_process_uptime',
            return_value=None,
        )

        call_command(CHECK_COMMAND, output_format='json')

        assert _json_lines(out=capsys.readouterr().out)[0] == {'event': 'startup', 'seconds': None}

    def test_cli_failure_exits_1_without_command_error_line(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        patch_check_managers.fail(alias='default', exc=AMQPConnectionError('boom'))

        with pytest.raises(SystemExit) as exc_info:
            Command().run_from_argv(argv=['manage.py', CHECK_COMMAND, '--format', 'json'])

        assert exc_info.value.code == 1
        captured: pytest.CaptureFixture[str] = capsys.readouterr()
        assert _json_lines(out=captured.out)[-1]['status'] == 'unhealthy'
        assert 'CommandError' not in captured.err

    def test_cli_does_not_run_system_checks(self, patch_check_managers: CheckManagers, mocker: MockerFixture) -> None:
        check: MagicMock = mocker.patch.object(Command, 'check')

        Command().run_from_argv(argv=['manage.py', CHECK_COMMAND])

        check.assert_not_called()

    def test_cli_accepts_legacy_skip_checks_flag(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        Command().run_from_argv(argv=['manage.py', CHECK_COMMAND, '--skip-checks'])

        assert capsys.readouterr().out.splitlines()[-1].startswith('HEALTHY ')

    def test_using_scopes_to_single_alias(
        self,
        patch_check_managers: CheckManagers,
        configure_rmq: Callable[[dict[str, dict[str, Any]]], None],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        configure_rmq({'default': DEFAULT_ALIAS_PARAMS, 'analytics': SECOND_ALIAS_PARAMS})

        call_command(CHECK_COMMAND, using='analytics', output_format='json')

        checks: list[dict[str, Any]] = [
            event for event in _json_lines(out=capsys.readouterr().out) if event['event'] == 'check'
        ]
        assert [check['alias'] for check in checks] == ['analytics']
        # The unselected alias is never touched.
        assert patch_check_managers.probed == ['analytics-node-2']

    def test_partial_failure_reports_only_failed(
        self,
        patch_check_managers: CheckManagers,
        configure_rmq: Callable[[dict[str, dict[str, Any]]], None],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        configure_rmq({'default': DEFAULT_ALIAS_PARAMS, 'analytics': SECOND_ALIAS_PARAMS})
        patch_check_managers.fail(alias='analytics', exc=AMQPConnectionError('boom'))

        with pytest.raises(CommandError) as exc_info:
            call_command(CHECK_COMMAND, output_format='json')

        message: str = str(exc_info.value)
        assert 'analytics' in message
        assert 'default' not in message
        summary: dict[str, Any] = _json_lines(out=capsys.readouterr().out)[-1]
        assert summary['healthy'] == 1
        assert summary['total'] == 2
        assert summary['failed'] == ['analytics']

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

        payloads: list[Any] = [r.msg for r in caplog.records if r.levelno == logging.WARNING]
        node_payload: Any = next(p for p in payloads if p['message'] == 'RabbitMQ node probe failed')
        assert node_payload['source'] == CHECK_COMMAND
        assert node_payload['data']['node'] == 'default-node-2:5672'
        payload: Any = next(p for p in payloads if p['message'] == 'RabbitMQ connection failed')
        assert payload['source'] == CHECK_COMMAND
        assert payload['data']['alias'] == 'default'
        assert 'boom' in payload['data']['error']
        assert isinstance(payload['data']['seconds'], float)

    def test_dead_first_node_does_not_fail_alias(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        patch_check_managers.set_nodes(alias='default', hosts=['rmq-1', 'rmq-2'])
        patch_check_managers.fail_node(host='rmq-1', exc=OSError('refused'))

        call_command(CHECK_COMMAND, output_format='json')

        check: dict[str, Any] = _json_lines(out=capsys.readouterr().out)[1]
        assert check['status'] == 'ok'
        assert check['node'] == 'rmq-2:5672'

    def test_hanging_first_node_does_not_delay_alias(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Nodes are probed in parallel: a node that never answers must not hold
        # back a live one listed after it.
        patch_check_managers.set_nodes(alias='default', hosts=['rmq-1', 'rmq-2'])
        patch_check_managers.hang_node(host='rmq-1')

        started_at: float = time.monotonic()
        call_command(CHECK_COMMAND, output_format='json', timeout=5)

        assert time.monotonic() - started_at < 1
        check: dict[str, Any] = _json_lines(out=capsys.readouterr().out)[1]
        assert check['status'] == 'ok'
        assert check['node'] == 'rmq-2:5672'

    def test_all_nodes_failed_reports_every_node_error(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        patch_check_managers.set_nodes(alias='default', hosts=['rmq-1', 'rmq-2'])
        patch_check_managers.fail_node(host='rmq-1', exc=OSError('refused'))
        patch_check_managers.fail_node(host='rmq-2', exc=AMQPConnectionError('auth'))

        with pytest.raises(CommandError, match='default'):
            call_command(CHECK_COMMAND, output_format='json')

        error: str = _json_lines(out=capsys.readouterr().out)[1]['error']
        assert sorted(error.split('; ')) == ['rmq-1:5672 OSError: refused', 'rmq-2:5672 AMQPConnectionError: auth']

    def test_deadline_fails_alias_without_answer(
        self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]
    ) -> None:
        patch_check_managers.set_nodes(alias='default', hosts=['rmq-1', 'rmq-2'])
        patch_check_managers.hang_node(host='rmq-1')
        patch_check_managers.fail_node(host='rmq-2', exc=OSError('refused'))

        started_at: float = time.monotonic()
        with pytest.raises(CommandError, match='default'):
            call_command(CHECK_COMMAND, output_format='json', timeout=0.2)

        assert 0.2 <= time.monotonic() - started_at < 1
        check: dict[str, Any] = _json_lines(out=capsys.readouterr().out)[1]
        assert check['status'] == 'fail'
        assert check['error'] == (
            'TimeoutError: no node answered within 0.2s; rmq-2:5672 OSError: refused; rmq-1:5672 no answer'
        )

    def test_deadline_and_node_timeouts_come_from_settings(
        self, patch_check_managers: CheckManagers, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            django_rmq,
            'healthcheck_config',
            HealthcheckConfig(deadline=0.2, socket_timeout=1.5, stack_timeout=2.5),
        )
        patch_check_managers.hang_node(host='default-node-2')

        with pytest.raises(CommandError):
            call_command(CHECK_COMMAND, output_format='json')

        assert patch_check_managers.probe_kwargs == {'socket_timeout': 1.5, 'stack_timeout': 2.5}
        assert 'within 0.2s' in _json_lines(out=capsys.readouterr().out)[1]['error']

    def test_default_deadline_without_settings(
        self, patch_check_managers: CheckManagers, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(django_rmq, 'healthcheck_config', None)

        call_command(CHECK_COMMAND)

        assert patch_check_managers.probe_kwargs == {'socket_timeout': 5.0, 'stack_timeout': 10.0}

    def test_aliases_are_checked_in_parallel(
        self,
        patch_check_managers: CheckManagers,
        configure_rmq: Callable[[dict[str, dict[str, Any]]], None],
    ) -> None:
        configure_rmq({'default': DEFAULT_ALIAS_PARAMS, 'analytics': SECOND_ALIAS_PARAMS})
        patch_check_managers.hang_node(host='default-node-2')
        patch_check_managers.hang_node(host='analytics-node-2')

        started_at: float = time.monotonic()
        with pytest.raises(CommandError):
            call_command(CHECK_COMMAND, timeout=0.3)

        # Sequential checks would take two deadlines; parallel ones take one.
        assert time.monotonic() - started_at < 0.55

    @pytest.mark.parametrize('timeout', [0, -1])
    def test_non_positive_timeout_is_rejected(self, patch_check_managers: CheckManagers, timeout: float) -> None:
        with pytest.raises(CommandError, match='--timeout'):
            call_command(CHECK_COMMAND, timeout=timeout)

        assert patch_check_managers.probed == []

    def test_cli_timeout_option(self, patch_check_managers: CheckManagers, capsys: pytest.CaptureFixture[str]) -> None:
        patch_check_managers.hang_node(host='default-node-2')

        with pytest.raises(SystemExit):
            Command().run_from_argv(argv=['manage.py', CHECK_COMMAND, '--timeout', '0.1'])

        assert 'within 0.1s' in capsys.readouterr().out

    def test_probe_threads_are_daemons(self, patch_check_managers: CheckManagers, mocker: MockerFixture) -> None:
        # Non-daemon threads would keep the probe process alive on a hanging node.
        thread: MagicMock = mocker.patch(f'django_rmq.management.commands.{CHECK_COMMAND}.threading.Thread')

        with pytest.raises(CommandError):
            call_command(CHECK_COMMAND, timeout=0.05)

        assert thread.call_args.kwargs['daemon'] is True


class TestProcessUptime:
    def test_reads_proc_on_linux(self, mocker: MockerFixture) -> None:
        # comm with spaces and parentheses must not shift the field indexes.
        stat: str = '42 (my (odd) proc) S ' + ' '.join(['0'] * 18) + ' 1000 rest'
        files: dict[str, str] = {'/proc/self/stat': stat, '/proc/uptime': '25.00 99.00'}
        mocker.patch(
            f'django_rmq.management.commands.{CHECK_COMMAND}.open',
            side_effect=lambda file, encoding: io.StringIO(files[file]),
            create=True,
        )
        mocker.patch(f'django_rmq.management.commands.{CHECK_COMMAND}.os.sysconf', return_value=100)

        # started at tick 1000 / 100 Hz = 10 s after boot; uptime 25 s → 15 s.
        assert Command._get_process_uptime() == pytest.approx(15.0)

    def test_returns_none_without_proc(self, mocker: MockerFixture) -> None:
        mocker.patch(
            f'django_rmq.management.commands.{CHECK_COMMAND}.open',
            side_effect=FileNotFoundError,
            create=True,
        )

        assert Command._get_process_uptime() is None
