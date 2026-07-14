from dataclasses import dataclass


@dataclass(frozen=True)
class NodeConfig:
    """
    Immutable address of a single RabbitMQ node within a connection alias.

    A cluster is expressed as several NodeConfig entries sharing the same
    credentials and virtual host on their parent RabbitMQConfig.

    :param host: Node hostname or IP address.
    :param port: Node AMQP port.
    """

    host: str
    port: int


@dataclass(frozen=True)
class RabbitMQConfig:
    """
    Immutable resolved configuration for a single RabbitMQ connection alias.

    An alias may point at one node (a plain broker) or several (a cluster).
    All nodes share the same virtual host and credentials; only their host
    and port differ.

    :param nodes: One or more node addresses to connect to. pika tries them in
                  order until one accepts the connection, giving client-side
                  failover across a cluster.
    :param virtual_host: AMQP virtual host to connect to.
    :param user: Username for PlainCredentials authentication.
    :param password: Password for PlainCredentials authentication.
    :param heartbeat: Heartbeat interval in seconds negotiated with the broker.
    :param blocked_connection_timeout: Seconds to wait while the broker
                                       blocks the connection before failing.
    :param reconnect_initial_backoff: Initial consumer reconnect delay in seconds.
    :param reconnect_max_backoff: Maximum consumer reconnect delay in seconds (cap
                                  for the exponential backoff).
    :param shuffle_nodes: When True, the node order is reshuffled on every
                          connection attempt so clients spread themselves across
                          the cluster instead of all preferring the first node.
    """

    nodes: tuple[NodeConfig, ...]
    virtual_host: str
    user: str
    password: str
    heartbeat: int
    blocked_connection_timeout: int
    reconnect_initial_backoff: float
    reconnect_max_backoff: float
    shuffle_nodes: bool = False
