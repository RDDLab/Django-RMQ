from typing import (
    List,
    Optional,
)

from django_rmq.consumer import Consumer
from django_rmq.utils import resolve_alias


class ConsumersRegistry:
    _consumers: List[Consumer]

    def __init__(self) -> None:
        self._consumers = []

    def register(self, consumer: Consumer) -> None:
        self._consumers.append(consumer)

    def all(self) -> List[Consumer]:
        return list(self._consumers)


def get_consumers_registry(using: Optional[str] = None) -> ConsumersRegistry:
    import django_rmq
    return resolve_alias(mapping=django_rmq.consumers_registries, using=using)
