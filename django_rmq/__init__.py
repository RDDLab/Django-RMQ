from typing import (
    Dict,
    Optional,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from django_rmq.connections import RabbitMQConnectionManager
    from django_rmq.registries.registry import ConsumersRegistry
    from django_rmq.registries.setup_registry import SetupRegistry

default_app_config = 'django_rmq.apps.RabbitMQAppConfig'  # pylint: disable=C0103
connection_managers: Optional[Dict[str, 'RabbitMQConnectionManager']] = None  # pylint: disable=C0103
setup_registries: Optional[Dict[str, 'SetupRegistry']] = None  # pylint: disable=C0103
consumers_registries: Optional[Dict[str, 'ConsumersRegistry']] = None  # pylint: disable=C0103
