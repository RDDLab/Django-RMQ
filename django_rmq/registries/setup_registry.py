from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
)

from django_rmq.utils import resolve_alias

if TYPE_CHECKING:
    from pika.adapters.blocking_connection import BlockingChannel

SetupFn = Callable[['BlockingChannel'], None]


class SetupRegistry:
    """
    Holds idempotent topology-setup functions for a single connection alias.

    The `setup_rabbitmq` management command opens a channel and runs every
    registered function to declare exchanges and queues on the broker.
    """

    _setups: list[SetupFn]

    def __init__(self) -> None:
        """
        Initializes an empty setup registry.
        """
        self._setups: list[SetupFn] = []

    def register(self, fn: SetupFn) -> None:
        """
        Adds a setup function to the registry.

        :param fn: A callable that receives an open BlockingChannel and declares
                   exchanges/queues on it. Must be idempotent.
        """
        self._setups.append(fn)

    def run_all(self, channel: 'BlockingChannel') -> None:
        """
        Runs every registered setup function on the given channel.

        :param channel: An open BlockingChannel passed to each setup function.
        """
        for fn in self._setups:
            fn(channel)


def get_setup_registry(using: str | None = None) -> SetupRegistry:
    """
    Returns the setup registry for the given alias.

    :param using: Connection alias from `RABBITMQ_CONNECTIONS`. May be omitted when
                  exactly one connection is configured. Required when there are several.
    :return: The SetupRegistry bound to the resolved alias.
    """
    import django_rmq

    return resolve_alias(mapping=django_rmq.setup_registries, using=using)
