from django_rmq.consumer import Consumer
from django_rmq.utils import resolve_alias


class ConsumersRegistry:
    """
    Holds the consumers registered for a single connection alias.

    The `start_consumers` management command iterates over every registered
    consumer and runs each one in its own thread.
    """

    _consumers: list[Consumer]

    def __init__(self) -> None:
        """
        Initializes an empty consumers registry.
        """
        self._consumers = []

    def register(self, consumer: Consumer) -> None:
        """
        Adds a consumer to the registry.

        :param consumer: The Consumer instance to register.
        """
        self._consumers.append(consumer)

    def all(self) -> list[Consumer]:
        """
        Returns all registered consumers.

        :return: A new list containing every registered Consumer (a copy, so the
                 caller cannot mutate the internal registry).
        """
        return list(self._consumers)


def get_consumers_registry(using: str | None = None) -> ConsumersRegistry:
    """
    Returns the consumer registry for the given alias.

    :param using: Connection alias from `RABBITMQ_CONNECTIONS`. May be omitted when
                  exactly one connection is configured. Required when there are several.
    :return: The ConsumersRegistry bound to the resolved alias.
    """
    import django_rmq

    return resolve_alias(mapping=django_rmq.consumers_registries, using=using)
