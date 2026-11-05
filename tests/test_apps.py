from typing import Any

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

import django_rmq
from django_rmq.dto.healthcheck_config import HealthcheckConfig


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

        assert [(node.host, node.port) for node in config.nodes] == [('broker-host', 5672)]
        assert config.shuffle_nodes is False
        assert config.reconnect_max_backoff == 30.0

    def test_empty_connections_raise(self) -> None:
        with override_settings(RABBITMQ_CONNECTIONS={}), pytest.raises(ImproperlyConfigured):
            _ready()

    def test_missing_connections_raise(self) -> None:
        with override_settings(RABBITMQ_CONNECTIONS=None), pytest.raises(ImproperlyConfigured):
            _ready()


def _cluster_params(shuffle: bool = False) -> dict[str, Any]:
    return {
        'NODES': [
            {'HOST': 'n1', 'PORT': 5672},
            {'HOST': 'n2', 'PORT': 5673},
        ],
        'VIRTUAL_HOST': '/',
        'USER': 'guest',
        'PASSWORD': 'guest',
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
        'SHUFFLE_NODES': shuffle,
    }


class TestClusterConfig:
    def test_nodes_form_resolves_every_node(self) -> None:
        with override_settings(RABBITMQ_CONNECTIONS={'cluster': _cluster_params(shuffle=True)}):
            _ready()

        assert django_rmq.connection_managers is not None
        config = django_rmq.connection_managers['cluster'].config

        assert [(node.host, node.port) for node in config.nodes] == [('n1', 5672), ('n2', 5673)]
        assert config.shuffle_nodes is True

    def test_legacy_host_port_resolves_single_node(self) -> None:
        with override_settings(RABBITMQ_CONNECTIONS={'default': _alias_params('broker-host')}):
            _ready()

        assert django_rmq.connection_managers is not None
        config = django_rmq.connection_managers['default'].config
        assert len(config.nodes) == 1

    def test_nodes_and_scalar_together_raise(self) -> None:
        params: dict[str, Any] = {**_cluster_params(), 'HOST': 'x', 'PORT': 5672}
        with override_settings(RABBITMQ_CONNECTIONS={'bad': params}), pytest.raises(ImproperlyConfigured):
            _ready()

    def test_no_node_addressing_raises(self) -> None:
        params: dict[str, Any] = _cluster_params()
        del params['NODES']
        with override_settings(RABBITMQ_CONNECTIONS={'bad': params}), pytest.raises(ImproperlyConfigured):
            _ready()

    def test_empty_nodes_raises(self) -> None:
        params: dict[str, Any] = {**_cluster_params(), 'NODES': []}
        with override_settings(RABBITMQ_CONNECTIONS={'bad': params}), pytest.raises(ImproperlyConfigured):
            _ready()

    def test_node_without_port_raises(self) -> None:
        params: dict[str, Any] = {**_cluster_params(), 'NODES': [{'HOST': 'n1'}]}
        with override_settings(RABBITMQ_CONNECTIONS={'bad': params}), pytest.raises(ImproperlyConfigured):
            _ready()


class TestConnectionTimeouts:
    def test_defaults_match_pika(self) -> None:
        with override_settings(RABBITMQ_CONNECTIONS={'default': _alias_params('a')}):
            _ready()

        assert django_rmq.connection_managers is not None
        config = django_rmq.connection_managers['default'].config
        assert config.socket_timeout == 10.0
        assert config.stack_timeout == 15.0

    def test_overrides_are_applied(self) -> None:
        params: dict[str, Any] = {**_alias_params('a'), 'SOCKET_TIMEOUT': 3, 'STACK_TIMEOUT': 6.5}
        with override_settings(RABBITMQ_CONNECTIONS={'default': params}):
            _ready()

        assert django_rmq.connection_managers is not None
        config = django_rmq.connection_managers['default'].config
        assert config.socket_timeout == 3.0
        assert isinstance(config.socket_timeout, float)
        assert config.stack_timeout == 6.5

    @pytest.mark.parametrize('key', ['SOCKET_TIMEOUT', 'STACK_TIMEOUT'])
    @pytest.mark.parametrize('value', [0, -1, '5', True, None])
    def test_invalid_value_raises(self, key: str, value: Any) -> None:
        params: dict[str, Any] = {**_alias_params('a'), key: value}
        with (
            override_settings(RABBITMQ_CONNECTIONS={'default': params}),
            pytest.raises(ImproperlyConfigured, match=f"alias 'default': '{key}'"),
        ):
            _ready()


class TestHealthcheckConfig:
    def test_defaults_without_setting(self) -> None:
        with override_settings(RABBITMQ_CONNECTIONS={'default': _alias_params('a')}):
            _ready()

        assert django_rmq.healthcheck_config == HealthcheckConfig(deadline=15.0, socket_timeout=5.0, stack_timeout=10.0)

    def test_partial_override_keeps_other_defaults(self) -> None:
        with override_settings(
            RABBITMQ_CONNECTIONS={'default': _alias_params('a')},
            RABBITMQ_HEALTHCHECK={'DEADLINE': 20},
        ):
            _ready()

        assert django_rmq.healthcheck_config == HealthcheckConfig(deadline=20.0, socket_timeout=5.0, stack_timeout=10.0)

    def test_full_override(self) -> None:
        with override_settings(
            RABBITMQ_CONNECTIONS={'default': _alias_params('a')},
            RABBITMQ_HEALTHCHECK={'DEADLINE': 12, 'SOCKET_TIMEOUT': 2, 'STACK_TIMEOUT': 4},
        ):
            _ready()

        assert django_rmq.healthcheck_config == HealthcheckConfig(deadline=12.0, socket_timeout=2.0, stack_timeout=4.0)

    def test_unknown_key_raises(self) -> None:
        with (
            override_settings(
                RABBITMQ_CONNECTIONS={'default': _alias_params('a')},
                RABBITMQ_HEALTHCHECK={'TIMEOUT': 10},
            ),
            pytest.raises(ImproperlyConfigured, match='unknown key'),
        ):
            _ready()

    def test_not_a_dict_raises(self) -> None:
        with (
            override_settings(RABBITMQ_CONNECTIONS={'default': _alias_params('a')}, RABBITMQ_HEALTHCHECK=15),
            pytest.raises(ImproperlyConfigured, match='must be a dict'),
        ):
            _ready()

    @pytest.mark.parametrize('key', ['DEADLINE', 'SOCKET_TIMEOUT', 'STACK_TIMEOUT'])
    def test_non_positive_value_raises(self, key: str) -> None:
        with (
            override_settings(RABBITMQ_CONNECTIONS={'default': _alias_params('a')}, RABBITMQ_HEALTHCHECK={key: 0}),
            pytest.raises(ImproperlyConfigured, match=f"'{key}'"),
        ):
            _ready()
