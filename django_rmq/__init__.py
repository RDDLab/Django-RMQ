from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django_rmq.connections import RabbitMQConnectionManager
    from django_rmq.registries.registry import ConsumersRegistry
    from django_rmq.registries.setup_registry import SetupRegistry

connection_managers: dict[str, 'RabbitMQConnectionManager'] | None = None
setup_registries: dict[str, 'SetupRegistry'] | None = None
consumers_registries: dict[str, 'ConsumersRegistry'] | None = None
