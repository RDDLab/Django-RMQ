import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType

from django_rmq.registries.setup_registry import get_setup_registry
from tests.integration.conftest import MgmtApi, Names, poll

pytestmark = pytest.mark.integration

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]
_RUNNER: Path = Path(__file__).parent / '_start_consumers_runner.py'


class TestCommands:
    """
    End-to-end tests for the shipped management commands against a real broker:
    `setup_rabbitmq_topology` declares real topology (idempotently), and
    `start_consumers` actually consumes a published message before a graceful stop.
    """

    def test_setup_rabbitmq_topology_declares_and_is_idempotent(
        self,
        configure_real_rmq,
        admin_channel: BlockingChannel,
        names: Names,
        mgmt_api: MgmtApi,
    ):
        configure_real_rmq()

        def setup(channel: BlockingChannel) -> None:
            channel.exchange_declare(exchange=names.exchange, exchange_type=ExchangeType.direct, durable=True)
            channel.queue_declare(queue=names.queue, durable=True)
            channel.queue_bind(queue=names.queue, exchange=names.exchange, routing_key='rk')

        get_setup_registry().register(fn=setup)

        call_command('setup_rabbitmq_topology')

        assert poll(lambda: mgmt_api.exchange_exists(names.exchange)), 'exchange not declared'
        assert poll(lambda: mgmt_api.queue(name=names.queue) is not None), 'queue not declared'

        # Re-running must not raise (all declarations are idempotent on RabbitMQ).
        call_command('setup_rabbitmq_topology')

    def test_start_consumers_consumes_then_stops(
        self,
        admin_channel: BlockingChannel,
        names: Names,
        mgmt_api: MgmtApi,
        tmp_path: Path,
    ):
        admin_channel.queue_declare(queue=names.queue, durable=True)
        output: Path = tmp_path / 'received.txt'

        env: dict[str, str] = {
            **os.environ,
            'IT_QUEUE': names.queue,
            'IT_OUTPUT': str(output),
            'PYTHONPATH': str(_REPO_ROOT),
            'DJANGO_SETTINGS_MODULE': 'tests.settings',
        }
        process: subprocess.Popen[bytes] = subprocess.Popen(
            [sys.executable, str(_RUNNER)],
            env=env,
            cwd=str(_REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            assert poll(lambda: mgmt_api.consumer_count(name=names.queue) >= 1, timeout=20), 'consumer never attached'

            admin_channel.basic_publish(exchange='', routing_key=names.queue, body=b'hello-cmd')

            assert poll(
                lambda: output.exists() and b'hello-cmd' in output.read_bytes(),
                timeout=20,
            ), 'message was not consumed by the command'
        finally:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def test_check_connections_ok(
        self,
        configure_real_rmq,
        capsys: pytest.CaptureFixture[str],
    ):
        configure_real_rmq()

        call_command('check_rabbitmq_connections')

        assert 'ok: default' in capsys.readouterr().out

    def test_check_connections_unreachable_raises(
        self,
        configure_real_rmq,
        broker_params: dict[str, Any],
    ):
        # A dead port makes the producer connection fail fast.
        configure_real_rmq({'default': {**broker_params, 'PORT': 1}})

        with pytest.raises(CommandError, match='default'):
            call_command('check_rabbitmq_connections')
