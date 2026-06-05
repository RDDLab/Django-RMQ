from dataclasses import dataclass
from typing import (
    Dict,
    Any,
    Optional
)



@dataclass(frozen=True)
class QueueConfig:
    name: str
    durable: bool = True
    dead_letter_exchange: Optional[str] = None
    dead_letter_routing_key: Optional[str] = None

    def __str__(self) -> str:
        return self.name

    @property
    def arguments(self) -> Optional[Dict[str, Any]]:
        args: Dict[str, Any] = {}
        if self.dead_letter_exchange is not None:
            args['x-dead-letter-exchange'] = self.dead_letter_exchange
        if self.dead_letter_routing_key is not None:
            args['x-dead-letter-routing-key'] = self.dead_letter_routing_key
        return args if args else None
