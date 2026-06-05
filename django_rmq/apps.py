from typing import (
    Any,
    Dict,
    Optional,
)

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured

from django_rmq.dto.rabbitmq_config import RabbitMQConfig


class RabbitMQAppConfig(AppConfig):
    name = 'django_rmq'

    def ready(self) -> None:
        from django.conf import settings
        from django_rmq.connections import RabbitMQConnectionManager
        from django_rmq.registries.registry import ConsumersRegistry
        from django_rmq.registries.setup_registry import SetupRegistry
        import django_rmq

        connections: Optional[Dict[str, Dict[str, Any]]] = getattr(settings, 'RABBITMQ_CONNECTIONS', None)
        if not connections:
            raise ImproperlyConfigured(
                'django_rmq requires `RABBITMQ_CONNECTIONS` in Django settings: '
                'a non-empty dict mapping alias -> connection params.'
            )

        connection_managers: Dict[str, RabbitMQConnectionManager] = {}
        setup_registries: Dict[str, SetupRegistry] = {}
        consumers_registries: Dict[str, ConsumersRegistry] = {}

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
