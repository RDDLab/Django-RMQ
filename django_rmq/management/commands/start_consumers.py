import logging
import signal
import threading

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import (
    BaseCommand,
    CommandParser,
)

import django_rmq
from django_rmq.consumer import Consumer
from django_rmq.registries.registry import get_consumers_registry

logger = logging.getLogger('rabbitmq')


class Command(BaseCommand):
    """
    Management command that starts all registered RabbitMQ consumers.

    Each registered consumer runs in its own thread sharing a single stop event.
    SIGTERM/SIGINT trigger a graceful shutdown, after which the command joins all
    threads before returning.
    """

    help = 'Start all registered RabbitMQ consumers'

    def add_arguments(self, parser: CommandParser) -> None:
        """
        Registers the command-line arguments.
        """
        parser.add_argument(
            '--using',
            dest='using',
            default=None,
            help='Connection alias from RABBITMQ_CONNECTIONS to start. If omitted, starts consumers for every alias.',
        )

    def handle(self, *args, **kwargs) -> None:
        """
        Starts the consumer threads for one or all aliases and waits for shutdown.

        :param kwargs: Parsed options; `using` selects a single alias, or starts
                       consumers for every alias when omitted.
        :raises ImproperlyConfigured: If django_rmq has not been initialized.
        """
        _source: str = 'start_consumers'
        using: str | None = kwargs.get('using')

        if django_rmq.consumers_registries is None:
            raise ImproperlyConfigured('django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.')

        if using is not None:
            aliases: list[str] = [using]
        else:
            aliases = list(django_rmq.consumers_registries.keys())

        pairs: list[tuple[str, Consumer]] = []
        for alias in aliases:
            for consumer in get_consumers_registry(using=alias).all():
                pairs.append((alias, consumer))

        if not pairs:
            logger.warning({'source': _source, 'message': 'No consumers registered'})
            return

        stop_event: threading.Event = threading.Event()

        def _signal_stop(*_args) -> None:
            logger.info({'source': _source, 'message': 'Stop signal received'})
            stop_event.set()

        signal.signal(signal.SIGTERM, _signal_stop)
        signal.signal(signal.SIGINT, _signal_stop)

        threads = []
        for alias, consumer in pairs:
            thread = threading.Thread(
                target=consumer.consume,
                kwargs={'stop_event': stop_event},
                name=f'consumer-{alias}-{consumer.queue}',
            )
            thread.start()
            logger.info(
                {
                    'source': _source,
                    'message': 'Consumer thread started',
                    'data': {'alias': alias, 'queue': consumer.queue},
                }
            )
            threads.append(thread)

        for thread in threads:
            thread.join()

        logger.info({'source': _source, 'message': 'All consumer threads stopped'})
