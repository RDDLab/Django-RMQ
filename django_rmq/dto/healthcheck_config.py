from dataclasses import dataclass


@dataclass(frozen=True)
class HealthcheckConfig:
    """
    Immutable configuration of the `check_rabbitmq_connections` healthcheck.

    Built from the optional `RABBITMQ_HEALTHCHECK` setting. The probe uses its
    own, shorter per-node timeouts instead of the alias ones, so a slow or dead
    node cannot push the probe past the orchestrator's timeout.

    :param deadline: Overall budget in seconds for checking every alias. When
                     it expires, aliases without a live node are reported as
                     failed and the command exits.
    :param socket_timeout: Seconds to wait for the TCP connection to a single node.
    :param stack_timeout: Seconds to wait for the full TCP + AMQP bring-up of a
                          single node.
    """

    deadline: float = 15.0
    socket_timeout: float = 5.0
    stack_timeout: float = 10.0
