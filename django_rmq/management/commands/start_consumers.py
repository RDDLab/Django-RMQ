import logging
import signal
import threading

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import CommandParser

import django_rmq
from django_rmq.consumer import Consumer
from django_rmq.management.commands.base_rdd_command import RDDBaseCommand
from django_rmq.management.enums.command_styles import CommandStyle
from django_rmq.registries.registry import get_consumers_registry

logger = logging.getLogger('rabbitmq')


class Command(RDDBaseCommand):
    """
    Management command that starts all registered RabbitMQ consumers.

    Each registered consumer runs in its own thread sharing a single stop event.
    SIGTERM/SIGINT trigger a graceful shutdown, after which the command joins all
    threads before returning.
    """

    help = 'Start all registered RabbitMQ consumers'

    def _print_consumers(self, consumers_by_alias: dict[str, list[Consumer]]) -> None:
        """
        Prints the consumers that are about to start, grouped by connection alias.

        Each alias is shown as a header followed by one line per consumer with its
        queue, prefetch count and registered handler. A trailing separator detaches
        the block from the log output that follows.

        :param consumers_by_alias: Mapping of connection alias to the consumers
                                   registered for it, in start order.
        """
        self.stdout.write(CommandStyle.BOLD_GREEN.apply(text='Consumers'))
        for alias, consumers in consumers_by_alias.items():
            self.stdout.write(CommandStyle.BOLD.apply(text=f'Alias: {alias}'))
            for index, consumer in enumerate(consumers):
                is_last: bool = index == len(consumers) - 1
                branch: str = '└─' if is_last else '├─'
                self.stdout.write(
                    f'  {branch} queue={consumer.queue}  '
                    f'prefetch_count={consumer.prefetch_count}  '
                    f'handler={consumer.handler_name} — Is consuming...'
                )

        self.stdout.write(self.style.SUCCESS(self._separator()))

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

        self._print_banner()

        if django_rmq.consumers_registries is None:
            raise ImproperlyConfigured('django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.')

        if using is not None:
            aliases: list[str] = [using]
        else:
            aliases = list(django_rmq.consumers_registries.keys())

        consumers_by_alias: dict[str, list[Consumer]] = {
            alias: list(get_consumers_registry(using=alias).all()) for alias in aliases
        }
        pairs: list[tuple[str, Consumer]] = [
            (alias, consumer) for alias, consumers in consumers_by_alias.items() for consumer in consumers
        ]

        if not pairs:
            logger.warning({'source': _source, 'message': 'No consumers registered'})
            return

        self._print_consumers(consumers_by_alias=consumers_by_alias)

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
