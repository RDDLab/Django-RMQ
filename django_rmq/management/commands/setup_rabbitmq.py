from typing import (
    List,
    Optional,
)

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import (
    BaseCommand,
    CommandParser,
)

import django_rmq
from django_rmq.connections import get_connection_manager
from django_rmq.registries.setup_registry import get_setup_registry


class Command(BaseCommand):
    help = 'Declare all RabbitMQ exchanges and queues (idempotent)'

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            '--using',
            dest='using',
            default=None,
            help='Connection alias from RABBITMQ_CONNECTIONS to set up. If omitted, runs for every alias.',
        )

    def handle(self, *args, **kwargs) -> None:
        using: Optional[str] = kwargs.get('using')

        if django_rmq.connection_managers is None:
            raise ImproperlyConfigured(
                'django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.'
            )

        if using is not None:
            aliases: List[str] = [using]
        else:
            aliases = list(django_rmq.connection_managers.keys())

        for alias in aliases:
            connection = get_connection_manager(using=alias).get_producer_connection()
            channel = connection.channel()
            try:
                get_setup_registry(using=alias).run_all(channel=channel)
            finally:
                if channel.is_open:
                    channel.close()
            self.stdout.write(self.style.SUCCESS(f'RabbitMQ setup complete for alias {alias!r}'))
