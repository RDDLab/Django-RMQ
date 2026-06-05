from dataclasses import dataclass


@dataclass(frozen=True)
class RabbitMQConfig:
    host: str
    port: int
    virtual_host: str
    user: str
    password: str
    heartbeat: int
    blocked_connection_timeout: int
    reconnect_initial_backoff: float
    reconnect_max_backoff: float
