from typing import Any

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured

from django_rmq.dto.healthcheck_config import HealthcheckConfig
from django_rmq.dto.rabbitmq_config import NodeConfig, RabbitMQConfig

_DEFAULT_SOCKET_TIMEOUT: float = 10.0
_DEFAULT_STACK_TIMEOUT: float = 15.0
_HEALTHCHECK_KEYS: frozenset[str] = frozenset({'DEADLINE', 'SOCKET_TIMEOUT', 'STACK_TIMEOUT'})


class RabbitMQAppConfig(AppConfig):
    """
    Django AppConfig for django_rmq.

    On `ready()` it reads the `RABBITMQ_CONNECTIONS` setting and builds, per
    alias, a connection manager plus an (initially empty) setup registry and
    consumer registry, exposing them as module-level attributes on `django_rmq`.
    """

    name = 'django_rmq'

    def ready(self) -> None:
        """
        Initializes django_rmq from the `RABBITMQ_CONNECTIONS` setting.

        Builds one RabbitMQConnectionManager, SetupRegistry, and ConsumersRegistry
        per configured alias and stores them on the `django_rmq` module so the
        rest of the library can resolve them by alias.

        :raises ImproperlyConfigured: If `RABBITMQ_CONNECTIONS` is missing or empty,
                                      or any setting value is invalid.
        """
        from django.conf import settings

        import django_rmq
        from django_rmq.connections import RabbitMQConnectionManager
        from django_rmq.registries.registry import ConsumersRegistry
        from django_rmq.registries.setup_registry import SetupRegistry

        connections: dict[str, dict[str, Any]] | None = getattr(settings, 'RABBITMQ_CONNECTIONS', None)
        if not connections:
            raise ImproperlyConfigured(
                'django_rmq requires `RABBITMQ_CONNECTIONS` in Django settings: '
                'a non-empty dict mapping alias -> connection params.'
            )

        connection_managers: dict[str, RabbitMQConnectionManager] = {}
        setup_registries: dict[str, SetupRegistry] = {}
        consumers_registries: dict[str, ConsumersRegistry] = {}

        for alias, params in connections.items():
            connection_managers[alias] = RabbitMQConnectionManager(
                config=self._build_config(alias=alias, params=params),
            )
            setup_registries[alias] = SetupRegistry()
            consumers_registries[alias] = ConsumersRegistry()

        django_rmq.connection_managers = connection_managers
        django_rmq.setup_registries = setup_registries
        django_rmq.consumers_registries = consumers_registries
        django_rmq.healthcheck_config = self._build_healthcheck_config(
            params=getattr(settings, 'RABBITMQ_HEALTHCHECK', None),
        )

    @classmethod
    def _build_config(cls, alias: str, params: dict[str, Any]) -> RabbitMQConfig:
        """
        Builds a RabbitMQConfig for a single alias from its settings dict.

        Node addresses come from either the multi-node `NODES` key or the
        scalar `HOST`/`PORT` pair — the two forms are mutually exclusive. All
        other keys (virtual host, credentials, timeouts, backoff) are shared
        across every node of the alias.

        :param alias: Connection alias, used only to make validation errors clear.
        :param params: The alias parameters dict from `RABBITMQ_CONNECTIONS`.
        :return: The resolved, immutable RabbitMQConfig.
        :raises ImproperlyConfigured: If node addressing is missing, empty, or
                                      specified via both `NODES` and `HOST`/`PORT`.
        """
        return RabbitMQConfig(
            nodes=cls._resolve_nodes(alias=alias, params=params),
            virtual_host=params['VIRTUAL_HOST'],
            user=params['USER'],
            password=params['PASSWORD'],
            heartbeat=params['HEARTBEAT'],
            blocked_connection_timeout=params['BLOCKED_CONNECTION_TIMEOUT'],
            reconnect_initial_backoff=params['RECONNECT_INITIAL_BACKOFF'],
            reconnect_max_backoff=params['RECONNECT_MAX_BACKOFF'],
            shuffle_nodes=params.get('SHUFFLE_NODES', False),
            socket_timeout=cls._resolve_timeout(
                owner=f'RabbitMQ alias {alias!r}',
                key='SOCKET_TIMEOUT',
                value=params.get('SOCKET_TIMEOUT', _DEFAULT_SOCKET_TIMEOUT),
            ),
            stack_timeout=cls._resolve_timeout(
                owner=f'RabbitMQ alias {alias!r}',
                key='STACK_TIMEOUT',
                value=params.get('STACK_TIMEOUT', _DEFAULT_STACK_TIMEOUT),
            ),
        )

    @classmethod
    def _build_healthcheck_config(cls, params: Any) -> HealthcheckConfig:
        """
        Builds the healthcheck configuration from the `RABBITMQ_HEALTHCHECK` setting.

        Every key is optional; missing keys keep the HealthcheckConfig defaults.

        :param params: The `RABBITMQ_HEALTHCHECK` dict, or None when it is not set.
        :return: The resolved, immutable HealthcheckConfig.
        :raises ImproperlyConfigured: If the setting is not a dict, has unknown
                                      keys, or holds a non-positive number.
        """
        if params is None:
            return HealthcheckConfig()
        if not isinstance(params, dict):
            raise ImproperlyConfigured('`RABBITMQ_HEALTHCHECK` must be a dict.')

        unknown: list[str] = sorted(set(params) - _HEALTHCHECK_KEYS)
        if unknown:
            raise ImproperlyConfigured(
                f'`RABBITMQ_HEALTHCHECK`: unknown key(s) {", ".join(unknown)}; '
                f'allowed: {", ".join(sorted(_HEALTHCHECK_KEYS))}.'
            )

        defaults: HealthcheckConfig = HealthcheckConfig()
        owner: str = '`RABBITMQ_HEALTHCHECK`'
        return HealthcheckConfig(
            deadline=cls._resolve_timeout(owner=owner, key='DEADLINE', value=params.get('DEADLINE', defaults.deadline)),
            socket_timeout=cls._resolve_timeout(
                owner=owner, key='SOCKET_TIMEOUT', value=params.get('SOCKET_TIMEOUT', defaults.socket_timeout)
            ),
            stack_timeout=cls._resolve_timeout(
                owner=owner, key='STACK_TIMEOUT', value=params.get('STACK_TIMEOUT', defaults.stack_timeout)
            ),
        )

    @classmethod
    def _resolve_timeout(cls, owner: str, key: str, value: Any) -> float:
        """
        Validates a timeout setting and converts it to float.

        :param owner: Human-readable owner of the setting, used in the error message.
        :param key: Setting key, used in the error message.
        :param value: The raw setting value.
        :return: The timeout in seconds.
        :raises ImproperlyConfigured: If the value is not a positive int or float.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ImproperlyConfigured(f"{owner}: '{key}' must be a positive number of seconds, got {value!r}.")
        return float(value)

    @classmethod
    def _resolve_nodes(cls, alias: str, params: dict[str, Any]) -> tuple[NodeConfig, ...]:
        """
        Resolves the tuple of node addresses for an alias.

        Accepts the multi-node `NODES` list (a cluster) or the legacy scalar
        `HOST`/`PORT` pair (a single node), but not both at once.

        :param alias: Connection alias, used only to make validation errors clear.
        :param params: The alias' parameters dict from `RABBITMQ_CONNECTIONS`.
        :return: A non-empty tuple of NodeConfig entries.
        :raises ImproperlyConfigured: If both forms are given, neither is given,
                                      `NODES` is empty, or a node lacks HOST/PORT.
        """
        has_nodes: bool = 'NODES' in params
        has_scalar: bool = 'HOST' in params or 'PORT' in params

        if has_nodes and has_scalar:
            raise ImproperlyConfigured(f"RabbitMQ alias {alias!r}: use either 'NODES' or 'HOST'/'PORT', not both.")
        if not has_nodes and not has_scalar:
            raise ImproperlyConfigured(
                f"RabbitMQ alias {alias!r}: define node addressing via 'NODES' or 'HOST'/'PORT'."
            )

        if has_scalar:
            return (NodeConfig(host=params['HOST'], port=params['PORT']),)

        nodes: list[dict[str, Any]] = params['NODES']
        if not nodes:
            raise ImproperlyConfigured(f"RabbitMQ alias {alias!r}: 'NODES' must be a non-empty list.")

        resolved: list[NodeConfig] = []
        for index, node in enumerate(nodes):
            if 'HOST' not in node or 'PORT' not in node:
                raise ImproperlyConfigured(
                    f"RabbitMQ alias {alias!r}: NODES[{index}] must define both 'HOST' and 'PORT'."
                )
            resolved.append(NodeConfig(host=node['HOST'], port=node['PORT']))
        return tuple(resolved)
