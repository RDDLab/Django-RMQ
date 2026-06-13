from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueueConfig:
    """
    Declarative configuration for a RabbitMQ queue.

    :param name: Queue name (also used as its string representation).
    :param durable: Whether the queue survives, a broker restarts.
    :param dead_letter_exchange: Optional exchange dead-lettered messages are
                                 routed to (sets x-dead-letter-exchange).
    :param dead_letter_routing_key: Optional routing key used when dead-lettering
                                    (sets x-dead-letter-routing-key).
    """

    name: str
    durable: bool = True
    dead_letter_exchange: str | None = None
    dead_letter_routing_key: str | None = None

    def __str__(self) -> str:
        """
        :return: The queue name.
        """
        return self.name

    @property
    def arguments(self) -> dict[str, Any] | None:
        """
        Builds the AMQP `arguments` dict for queue declaration.

        :return: A dict with the configured x-dead-letter-* arguments, or None if
                 no dead-letter settings are present.
        """
        args: dict[str, Any] = {}
        if self.dead_letter_exchange is not None:
            args['x-dead-letter-exchange'] = self.dead_letter_exchange
        if self.dead_letter_routing_key is not None:
            args['x-dead-letter-routing-key'] = self.dead_letter_routing_key
        return args if args else None
