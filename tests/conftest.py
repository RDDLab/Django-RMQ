"""
Shared fixtures for the django_rmq test suite.

Two concerns are handled here:

1. **Module-level state isolation.** `RabbitMQAppConfig.ready()` stores the
   per-alias connection managers and registries as attributes on the
   `django_rmq` module. Tests that reconfigure aliases mutate that global
   state, so every test runs against a snapshot that is restored afterwards.

2. **pika mocking.** Unit tests never dial a real broker. The `mock_*`
   fixtures provide MagicMock channels/connections, and `patch_blocking_connection`
   replaces `pika.BlockingConnection` at the point `connections.py` imports it.
"""

from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

import django_rmq
from django_rmq.connections import RabbitMQConnectionManager
from django_rmq.dto.rabbitmq_config import RabbitMQConfig
from django_rmq.registries.registry import ConsumersRegistry
from django_rmq.registries.setup_registry import SetupRegistry

# The canonical single-alias broker params, mirroring the 'default' alias in
# tests.settings. Shared by tests that rebuild aliases via `configure_rmq`, so
# the shape of an alias entry is defined in exactly one place.
DEFAULT_ALIAS_PARAMS: dict[str, Any] = {
    'HOST': 'localhost',
    'PORT': 5672,
    'VIRTUAL_HOST': '/',
    'USER': 'guest',
    'PASSWORD': 'guest',
    'HEARTBEAT': 600,
    'BLOCKED_CONNECTION_TIMEOUT': 300,
    'RECONNECT_INITIAL_BACKOFF': 1.0,
    'RECONNECT_MAX_BACKOFF': 30.0,
}

# A second alias used by multi-alias tests, alongside the 'default' one that
# tests.settings already configures.
SECOND_ALIAS_PARAMS: dict[str, Any] = {
    'HOST': 'analytics-host',
    'PORT': 5672,
    'VIRTUAL_HOST': '/analytics',
    'USER': 'guest',
    'PASSWORD': 'guest',
    'HEARTBEAT': 600,
    'BLOCKED_CONNECTION_TIMEOUT': 300,
    'RECONNECT_INITIAL_BACKOFF': 1.0,
    'RECONNECT_MAX_BACKOFF': 30.0,
}


def _build_config(params: dict[str, Any]) -> RabbitMQConfig:
    """
    Builds a RabbitMQConfig from a RABBITMQ_CONNECTIONS-style alias dict.
    """
    return RabbitMQConfig(
        host=params['HOST'],
        port=params['PORT'],
        virtual_host=params['VIRTUAL_HOST'],
        user=params['USER'],
        password=params['PASSWORD'],
        heartbeat=params['HEARTBEAT'],
        blocked_connection_timeout=params['BLOCKED_CONNECTION_TIMEOUT'],
        reconnect_initial_backoff=params['RECONNECT_INITIAL_BACKOFF'],
        reconnect_max_backoff=params['RECONNECT_MAX_BACKOFF'],
    )


@pytest.fixture(autouse=True)
def reset_rmq_state() -> Iterator[None]:
    """
    Rebuilds the module-level django_rmq state from settings after every test.

    Restoring only the mapping references is not enough: registering a consumer
    or setup function mutates the registry object *inside* the mapping, which
    would leak across tests. Re-running `AppConfig.ready()` in teardown rebuilds
    fresh, empty registries and the single-alias managers from `tests.settings`,
    guaranteeing each test starts clean.
    """
    yield
    from django.apps import apps as django_apps

    django_apps.get_app_config('django_rmq').ready()


@pytest.fixture
def configure_rmq() -> Callable[[dict[str, dict[str, Any]]], None]:
    """
    Returns a helper that initializes django_rmq globals from a connections dict.

    The helper rebuilds the per-alias connection managers and (empty) registries,
    exactly like `RabbitMQAppConfig.ready()`, and installs them on the django_rmq
    module. `restore_rmq_globals` reverts the change after the test.

    :return: Callable taking a RABBITMQ_CONNECTIONS-style mapping.
    """

    def _configure(connections: dict[str, dict[str, Any]]) -> None:
        django_rmq.connection_managers = {
            alias: RabbitMQConnectionManager(config=_build_config(params=params))
            for alias, params in connections.items()
        }
        django_rmq.setup_registries = {alias: SetupRegistry() for alias in connections}
        django_rmq.consumers_registries = {alias: ConsumersRegistry() for alias in connections}

    return _configure


@pytest.fixture
def mock_channel() -> MagicMock:
    """
    Returns a MagicMock standing in for a pika BlockingChannel (open by default).
    """
    channel = MagicMock(name='BlockingChannel')
    channel.is_open = True
    return channel


@pytest.fixture
def mock_connection(mock_channel: MagicMock) -> MagicMock:
    """
    Returns a MagicMock BlockingConnection whose `.channel()` yields mock_channel.
    """
    connection = MagicMock(name='BlockingConnection')
    connection.is_open = True
    connection.channel.return_value = mock_channel
    return connection


@pytest.fixture
def patch_blocking_connection(mocker: MockerFixture, mock_connection: MagicMock) -> MagicMock:
    """
    Patches `pika.BlockingConnection` as imported in `connections.py`.

    Every `RabbitMQConnectionManager` connection open then returns `mock_connection`
    instead of dialing a broker.

    :return: The mock_connection that the manager will hand out.
    """
    mocker.patch('django_rmq.connections.BlockingConnection', return_value=mock_connection)
    return mock_connection
