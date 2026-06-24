from typing import Any

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

import django_rmq


def _alias_params(host: str) -> dict[str, Any]:
    return {
        'HOST': host,
        'PORT': 5672,
        'VIRTUAL_HOST': '/',
        'USER': 'guest',
        'PASSWORD': 'guest',
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    }


def _ready() -> None:
    django_apps.get_app_config('django_rmq').ready()


class TestAppReady:
    def test_builds_one_set_per_alias(self) -> None:
        connections = {'default': _alias_params('a'), 'analytics': _alias_params('b')}
        with override_settings(RABBITMQ_CONNECTIONS=connections):
            _ready()

        assert django_rmq.connection_managers is not None
        assert django_rmq.setup_registries is not None
        assert django_rmq.consumers_registries is not None
        assert set(django_rmq.connection_managers) == {'default', 'analytics'}
        assert set(django_rmq.setup_registries) == {'default', 'analytics'}
        assert set(django_rmq.consumers_registries) == {'default', 'analytics'}

    def test_manager_receives_resolved_config(self) -> None:
        with override_settings(RABBITMQ_CONNECTIONS={'default': _alias_params('broker-host')}):
            _ready()

        assert django_rmq.connection_managers is not None
        config = django_rmq.connection_managers['default'].config

        assert config.host == 'broker-host'
        assert config.reconnect_max_backoff == 30.0

    def test_empty_connections_raise(self) -> None:
        with override_settings(RABBITMQ_CONNECTIONS={}), pytest.raises(ImproperlyConfigured):
            _ready()

    def test_missing_connections_raise(self) -> None:
        with override_settings(RABBITMQ_CONNECTIONS=None), pytest.raises(ImproperlyConfigured):
            _ready()
