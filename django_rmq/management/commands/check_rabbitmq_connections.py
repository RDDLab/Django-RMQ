import logging
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import (
    BaseCommand,
    CommandError,
    CommandParser,
)
from pika.exceptions import AMQPError

import django_rmq
from django_rmq.connections import get_connection_manager
from django_rmq.management.enums.command_styles import CommandStyle

logger = logging.getLogger('rabbitmq')


class Command(BaseCommand):
    """
    Management command that verifies RabbitMQ connectivity.

    Opens a connection per alias and closes it immediately, reporting which
    aliases are reachable. Intended as a healthcheck.
    """

    help = 'Healthcheck: ensure all (or a specific) RabbitMQ connection(s) are reachable.'

    def add_arguments(self, parser: CommandParser) -> None:
        """
        Registers the command-line arguments.
        """
        parser.add_argument(
            '--using',
            dest='using',
            default=None,
            help='Connection alias from RABBITMQ_CONNECTIONS to check. If omitted, checks every alias.',
        )

    def handle(self, *args: Any, **kwargs: Any) -> None:
        """
        Checks connectivity for one or all aliases.

        :param kwargs: Parsed options; `using` selects a single alias, or checks
                       every alias when omitted.
        :raises ImproperlyConfigured: If django_rmq has not been initialized.
        :raises CommandError: If any checked alias is unreachable.
        """
        _source: str = 'check_rabbitmq_connections'
        using: str | None = kwargs.get('using')

        if django_rmq.connection_managers is None:
            raise ImproperlyConfigured('django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.')

        if using is not None:
            aliases: list[str] = [using]
        else:
            aliases = list(django_rmq.connection_managers.keys())

        failed: list[str] = []
        for alias in aliases:
            if self._check_alias(alias=alias, source=_source):
                self.stdout.write(CommandStyle.BOLD_GREEN.apply(text=f'  OK: {alias}'))
            else:
                self.stderr.write(self.style.ERROR(f'  FAIL: {alias}'))
                failed.append(alias)

        if failed:
            raise CommandError(f'unhealthy: {", ".join(failed)}')

        self.stdout.write(CommandStyle.BOLD_GREEN.apply(text=f'ok: {", ".join(aliases)}'))

    @classmethod
    def _check_alias(cls, alias: str, source: str) -> bool:
        """
        Opens and closes a connection for a single alias.

        :param alias: Connection alias from `RABBITMQ_CONNECTIONS` to check.
        :param source: Source identifier used for logging.
        :return: True if the connection was established successfully, otherwise False.
        """
        try:
            connection = get_connection_manager(using=alias).get_producer_connection()
            connection.close()
        except (AMQPError, OSError) as exc:
            logger.warning(
                {
                    'source': source,
                    'message': 'RabbitMQ connection failed',
                    'data': {'alias': alias, 'error': str(exc)},
                }
            )
            return False

        logger.debug(
            {
                'source': source,
                'message': 'RabbitMQ connection OK',
                'data': {'alias': alias},
            }
        )
        return True
