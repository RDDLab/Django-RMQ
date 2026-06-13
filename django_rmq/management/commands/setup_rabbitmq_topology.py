from typing import (
    TYPE_CHECKING,
    Any,
)

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import CommandParser
from django.utils.termcolors import make_style
from pika.exchange_type import ExchangeType

import django_rmq
from django_rmq.connections import get_connection_manager
from django_rmq.management.commands.base_rdd_command import RDDBaseCommand
from django_rmq.registries.setup_registry import get_setup_registry

if TYPE_CHECKING:
    from pika.adapters.blocking_connection import BlockingChannel

    _ChannelBase = BlockingChannel
else:
    _ChannelBase = object


class RecordingChannel(_ChannelBase):
    """
    Transparent proxy around a `BlockingChannel` that records the exchanges and
    queues declared on it.

    Setup functions registered in a `SetupRegistry` call `exchange_declare` and
    `queue_declare` on the channel they receive. Wrapping the real channel in
    this proxy lets the command report exactly what topology was declared
    without changing the setup-function contract: every other attribute access
    is delegated to the wrapped channel, so it behaves like a normal channel.
    """

    # noinspection PyMissingConstructor
    def __init__(self, channel: 'BlockingChannel') -> None:
        """
        :param channel: The real BlockingChannel to delegate every call to.

        The `BlockingChannel` base exists only for static typing (see
        `_ChannelBase`); at runtime this is a plain object, so its constructor
        is intentionally not invoked.
        """
        self._channel: BlockingChannel = channel
        self.exchanges: list[dict[str, Any]] = []
        self.queues: list[dict[str, Any]] = []
        self.bindings: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        """
        Delegates any non-overridden attribute access to the wrapped channel.

        :param name: Attribute name requested on the proxy.
        :return: The corresponding attribute of the wrapped channel.
        """
        return getattr(self._channel, name)

    def exchange_declare(self, exchange: str = '', exchange_type: str = ExchangeType.direct, **kwargs: Any) -> Any:
        """
        Records the exchange declaration and forwards it to the real channel.

        :param exchange: Exchange name being declared.
        :param exchange_type: AMQP exchange type (direct, topic, fanout, headers).
        :param kwargs: Remaining `exchange_declare` arguments passed through verbatim.
        :return: The result of the underlying `exchange_declare` call.
        """
        self.exchanges.append({'name': exchange, 'type': exchange_type})
        return self._channel.exchange_declare(exchange=exchange, exchange_type=exchange_type, **kwargs)

    def queue_declare(self, queue: str = '', **kwargs: Any) -> Any:
        """
        Records the queue declaration and forwards it to the real channel.

        :param queue: Queue name being declared.
        :param kwargs: Remaining `queue_declare` arguments passed through verbatim
                       (`arguments` is captured for reporting, e.g. dead-letter config).
        :return: The result of the underlying `queue_declare` call.
        """
        self.queues.append({'name': queue, 'arguments': kwargs.get('arguments')})
        return self._channel.queue_declare(queue=queue, **kwargs)

    def queue_bind(self, queue: str, exchange: str, routing_key: str | None = None, **kwargs: Any) -> Any:
        """
        Records the queue binding and forwards it to the real channel.

        :param queue: Queue being bound.
        :param exchange: Exchange the queue is bound to.
        :param routing_key: Routing key for the binding (may be omitted for fanout).
        :param kwargs: Remaining `queue_bind` arguments passed through verbatim.
        :return: The result of the underlying `queue_bind` call.
        """
        self.bindings.append({'queue': queue, 'exchange': exchange, 'routing_key': routing_key})
        return self._channel.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key, **kwargs)


class Command(RDDBaseCommand):
    """
    Management command that declares all RabbitMQ exchanges and queues.

    Opens a channel per alias and runs the corresponding `SetupRegistry`. The
    operation is idempotent, so it is safe to run on every deploy.
    """

    help = 'Declare all RabbitMQ exchanges and queues (idempotent)'

    def add_arguments(self, parser: CommandParser) -> None:
        """
        Registers the command-line arguments.

        """
        parser.add_argument(
            '--using',
            dest='using',
            default=None,
            help='Connection alias from RABBITMQ_CONNECTIONS to set up. If omitted, runs for every alias.',
        )

    def handle(self, *args, **kwargs) -> None:
        """
        Runs the topology setup for one or all aliases.

        :param kwargs: Parsed options; `using` selects a single alias, or starts
                       consumers for every alias when omitted.

        :raises ImproperlyConfigured: If django_rmq has not been initialized.
        """
        using: str | None = kwargs.get('using')

        self._print_banner()

        if django_rmq.connection_managers is None:
            raise ImproperlyConfigured('django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.')

        if using is not None:
            aliases: list[str] = [using]
        else:
            aliases = list(django_rmq.connection_managers.keys())

        for alias in aliases:
            connection = get_connection_manager(using=alias).get_producer_connection()
            channel = connection.channel()
            recording_channel = RecordingChannel(channel=channel)
            try:
                get_setup_registry(using=alias).run_all(channel=recording_channel)
            finally:
                if channel.is_open:
                    channel.close()
            self.stdout.write(self.style.SUCCESS(f'RabbitMQ setup complete for alias {alias!r}'))
            self._report_topology(recording_channel=recording_channel)

    def _bold(self, text: str) -> str:
        """
        Returns the text in bold, honoring the command's color settings.

        :param text: Text to embolden.
        :return: The bold text, or the unchanged text when the color is off.
        """
        if self.style.SUCCESS('probe') == 'probe':
            return text
        return make_style(opts=('bold',))(text)

    def _report_topology(self, recording_channel: RecordingChannel) -> None:
        """
        Writes the exchanges and queues declared during setup.

        Declarations are de-duplicated by name (setup functions are idempotent
        and may declare the same entity more than once), preserving first-seen
        order.

        :param recording_channel: The proxy that captured the declarations.
        """
        exchanges_by_name: dict[str, dict[str, Any]] = {}
        for exchange in recording_channel.exchanges:
            exchanges_by_name.setdefault(exchange['name'], exchange)

        queues_by_name: dict[str, dict[str, Any]] = {}
        for queue in recording_channel.queues:
            queues_by_name.setdefault(queue['name'], queue)

        bindings_by_key: dict[tuple[str, str | None, str], dict[str, Any]] = {}
        for binding in recording_channel.bindings:
            binding_key: tuple[str, str | None, str] = (
                binding['exchange'],
                binding['routing_key'],
                binding['queue'],
            )
            bindings_by_key.setdefault(binding_key, binding)

        self.stdout.write(self._bold(f'  Exchanges ({len(exchanges_by_name)}):'))
        if exchanges_by_name:
            for exchange in exchanges_by_name.values():
                name: str = exchange['name'] or '(default)'
                self.stdout.write(f'    - {name} [{exchange["type"]}]')
        else:
            self.stdout.write('    (none)')

        self.stdout.write(self._bold(f'  Queues ({len(queues_by_name)}):'))
        if queues_by_name:
            for queue in queues_by_name.values():
                arguments: dict[str, Any] | None = queue['arguments']
                suffix: str = f' {arguments}' if arguments else ''
                self.stdout.write(f'    - {queue["name"]}{suffix}')
        else:
            self.stdout.write('    (none)')

        self.stdout.write(self._bold(f'  Bindings ({len(bindings_by_key)}):'))
        if bindings_by_key:
            for binding in bindings_by_key.values():
                routing_key: str = binding['routing_key'] or '(none)'
                self.stdout.write(f'    - {binding["exchange"] or "(default)"} --[{routing_key}]--> {binding["queue"]}')
        else:
            self.stdout.write('    (none)')
