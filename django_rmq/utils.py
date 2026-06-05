from typing import (
    Dict,
    Optional,
    TypeVar,
)

from django.core.exceptions import ImproperlyConfigured

T = TypeVar('T')


def resolve_alias(mapping: Optional[Dict[str, T]], using: Optional[str] = None) -> T:
    if mapping is None:
        raise ImproperlyConfigured(
            'django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.'
        )
    if using is None:
        if len(mapping) == 1:
            return next(iter(mapping.values()))
        multiple_rabbitmq_connections_configured: str = (
            'Multiple RabbitMQ connections configured ('
            + ', '.join(sorted(mapping.keys()))
            + "); pass `using='<alias>'` explicitly."
        )
        raise ImproperlyConfigured(multiple_rabbitmq_connections_configured)
    value = mapping.get(using)
    if value is None:
        unknown_rabbit_mq_alias: str = f'Unknown RabbitMQ alias {using!r}.'
        raise ImproperlyConfigured(unknown_rabbit_mq_alias)
    return value
