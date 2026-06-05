import logging
import signal
import threading
from typing import (
    List,
    Optional,
    Tuple,
)

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
    help = 'Start all registered RabbitMQ consumers'

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            '--using',
            dest='using',
            default=None,
            help='Connection alias from RABBITMQ_CONNECTIONS to start. If omitted, starts consumers for every alias.',
        )

    def handle(self, *args, **kwargs) -> None:
        source = 'start_consumers'
        using: Optional[str] = kwargs.get('using')

        if django_rmq.consumers_registries is None:
            raise ImproperlyConfigured(
                'django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.'
            )

        if using is not None:
            aliases: List[str] = [using]
        else:
            aliases = list(django_rmq.consumers_registries.keys())

        pairs: List[Tuple[str, Consumer]] = []
        for alias in aliases:
            for consumer in get_consumers_registry(using=alias).all():
                pairs.append((alias, consumer))

        if not pairs:
            logger.warning({'source': source, 'message': 'No consumers registered'})
            return

        stop_event = threading.Event()

        def _signal_stop(*_args) -> None:
            logger.info({'source': source, 'message': 'Stop signal received'})
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
                    'source': source,
                    'message': 'Consumer thread started',
                    'data': {'alias': alias, 'queue': consumer.queue},
                }
            )
            threads.append(thread)

        for thread in threads:
            thread.join()

        logger.info({'source': source, 'message': 'All consumer threads stopped'})
