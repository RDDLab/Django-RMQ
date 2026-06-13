from typing import TypeVar

from django.core.exceptions import ImproperlyConfigured

T = TypeVar('T')


def resolve_alias(mapping: dict[str, T] | None, using: str | None = None) -> T:
    """
    Resolves a single value from an alias-keyed mapping.

    When `using` is omitted and the mapping holds exactly one entry, that entry
    is returned. When several aliases exist, `using` is required to disambiguate.

    :param mapping: Alias -> value mapping (e.g. connection managers or registries),
                    or None if django_rmq has not been initialized.
    :param using: Explicit alias to look up. May be omitted only when the mapping
                  contains exactly one entry.
    :return: The value bound to the resolved alias.
    :raises ImproperlyConfigured: If the mapping is None (app not initialized),
                                   if `using` is omitted while several aliases
                                   exist, or if `using` is unknown.
    """
    if mapping is None:
        raise ImproperlyConfigured('django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.')
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
