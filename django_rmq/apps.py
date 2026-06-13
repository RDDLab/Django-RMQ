from typing import Any

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured

from django_rmq.dto.rabbitmq_config import RabbitMQConfig


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

        :raises ImproperlyConfigured: If `RABBITMQ_CONNECTIONS` is missing or empty.
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
                config=RabbitMQConfig(
                    host=params['HOST'],
                    port=params['PORT'],
                    virtual_host=params['VIRTUAL_HOST'],
                    user=params['USER'],
                    password=params['PASSWORD'],
                    heartbeat=params['HEARTBEAT'],
                    blocked_connection_timeout=params['BLOCKED_CONNECTION_TIMEOUT'],
                    reconnect_initial_backoff=params['RECONNECT_INITIAL_BACKOFF'],
                    reconnect_max_backoff=params['RECONNECT_MAX_BACKOFF'],
                ),
            )
            setup_registries[alias] = SetupRegistry()
            consumers_registries[alias] = ConsumersRegistry()

        django_rmq.connection_managers = connection_managers
        django_rmq.setup_registries = setup_registries
        django_rmq.consumers_registries = consumers_registries
