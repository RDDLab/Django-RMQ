from dataclasses import dataclass
from enum import Enum
from typing import Any


class QueueType(str, Enum):
    """
    Supported RabbitMQ queue types (the `x-queue-type` declaration argument).

    Subclassing `str` (instead of 3.11+ `StrEnum`, unavailable on Python 3.10)
    makes each member an actual string, so its value is serialized to the broker
    as-is. When left unset on a `QueueConfig`, the broker applies its own
    `default_queue_type` (classic unless configured otherwise).
    """

    CLASSIC = 'classic'
    QUORUM = 'quorum'
    STREAM = 'stream'


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
    :param queue_type: Optional queue type (sets x-queue-type). When None the
                       broker applies its own default_queue_type.
    """

    name: str
    durable: bool = True
    dead_letter_exchange: str | None = None
    dead_letter_routing_key: str | None = None
    queue_type: QueueType | None = None

    def __str__(self) -> str:
        """
        :return: The queue name.
        """
        return self.name

    @property
    def arguments(self) -> dict[str, Any] | None:
        """
        Builds the AMQP `arguments` dict for queue declaration.

        :return: A dict with the configured x-queue-type and x-dead-letter-*
                 arguments, or None if none of them are present.
        """
        args: dict[str, Any] = {}
        if self.queue_type is not None:
            args['x-queue-type'] = self.queue_type.value
        if self.dead_letter_exchange is not None:
            args['x-dead-letter-exchange'] = self.dead_letter_exchange
        if self.dead_letter_routing_key is not None:
            args['x-dead-letter-routing-key'] = self.dead_letter_routing_key
        return args if args else None
