from dataclasses import dataclass


@dataclass(frozen=True)
class RabbitMQConfig:
    """
    Immutable resolved configuration for a single RabbitMQ connection alias.

    :param host: Broker hostname or IP address.
    :param port: Broker AMQP port.
    :param virtual_host: AMQP virtual host to connect to.
    :param user: Username for PlainCredentials authentication.
    :param password: Password for PlainCredentials authentication.
    :param heartbeat: Heartbeat interval in seconds negotiated with the broker.
    :param blocked_connection_timeout: Seconds to wait while the broker
                                       blocks the connection before failing.
    :param reconnect_initial_backoff: Initial consumer reconnect delay in seconds.
    :param reconnect_max_backoff: Maximum consumer reconnect delay in seconds (cap
                                  for the exponential backoff).
    """

    host: str
    port: int
    virtual_host: str
    user: str
    password: str
    heartbeat: int
    blocked_connection_timeout: int
    reconnect_initial_backoff: float
    reconnect_max_backoff: float
