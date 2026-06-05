from typing import (
    Callable,
    List,
    Optional,
    TYPE_CHECKING,
)

from django_rmq.utils import resolve_alias

if TYPE_CHECKING:
    from pika.adapters.blocking_connection import BlockingChannel

SetupFn = Callable[['BlockingChannel'], None]


class SetupRegistry:
    _setups: List[SetupFn]

    def __init__(self) -> None:
        self._setups: List[SetupFn] = []

    def register(self, fn: SetupFn) -> None:
        self._setups.append(fn)

    def run_all(self, channel: 'BlockingChannel') -> None:
        for fn in self._setups:
            fn(channel)


def get_setup_registry(using: Optional[str] = None) -> SetupRegistry:
    import django_rmq
    return resolve_alias(mapping=django_rmq.setup_registries, using=using)
