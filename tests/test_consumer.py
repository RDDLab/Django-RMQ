import threading
from unittest.mock import MagicMock

import pytest
from pika.exceptions import AMQPConnectionError
from pytest_mock import MockerFixture

from django_rmq.consumer import Consumer
from django_rmq.queues.queue_config import QueueConfig, QueueType


def _noop_handler(ch: object, method: object, props: object, body: bytes) -> None:
    """A handler that does nothing — used where the body is irrelevant."""


class TestHandlerRegistration:
    def test_handler_registers_callback(self) -> None:
        consumer = Consumer(queue='orders')
        returned = consumer.handler(func=_noop_handler)
        assert returned is _noop_handler
        assert consumer.handler_name == '_noop_handler'

    def test_call_is_shorthand_for_handler(self) -> None:
        consumer = Consumer(queue='orders')
        consumer(_noop_handler)
        assert consumer.handler_name == '_noop_handler'

    def test_second_handler_raises(self) -> None:
        consumer = Consumer(queue='orders')
        consumer.handler(func=_noop_handler)
        with pytest.raises(RuntimeError, match='already has a handler'):
            consumer.handler(func=_noop_handler)

    def test_handler_name_is_unregistered_when_none(self) -> None:
        assert Consumer(queue='orders').handler_name == 'unregistered'


class TestConsumeGuards:
    def test_consume_without_handler_returns_early(self, mocker: MockerFixture) -> None:
        get_manager = mocker.patch('django_rmq.consumer.get_connection_manager')
        Consumer(queue='orders').consume()
        # It bails out before ever resolving a connection manager.
        get_manager.assert_not_called()


class TestReconnectLoop:
    def _make_consumer(self, **kwargs: object) -> Consumer:
        consumer = Consumer(queue='orders', **kwargs)  # type: ignore[arg-type]
        consumer.handler(func=_noop_handler)
        return consumer

    def test_clean_session_returns_without_reconnect(self, mocker: MockerFixture) -> None:
        consumer = self._make_consumer()
        run_session = mocker.patch.object(consumer, '_run_session')
        stop_event = threading.Event()
        wait = mocker.patch.object(stop_event, 'wait')

        consumer.consume(stop_event=stop_event)

        run_session.assert_called_once()
        wait.assert_not_called()

    def test_backoff_doubles_and_caps_at_max(self, mocker: MockerFixture) -> None:
        consumer = self._make_consumer(reconnect_initial_backoff=1.0, reconnect_max_backoff=4.0)
        mocker.patch.object(consumer, '_run_session', side_effect=AMQPConnectionError('drop'))
        stop_event = threading.Event()

        timeouts: list[float] = []

        def fake_wait(timeout: float | None = None) -> bool:
            timeouts.append(timeout)  # type: ignore[arg-type]
            # Stop after enough iterations to observe the cap.
            if len(timeouts) >= 4:
                stop_event.set()
            return stop_event.is_set()

        mocker.patch.object(stop_event, 'wait', side_effect=fake_wait)
        consumer.consume(stop_event=stop_event)

        assert timeouts == [1.0, 2.0, 4.0, 4.0]

    def test_backoff_taken_from_config_when_no_override(self, mocker: MockerFixture) -> None:
        # tests.settings uses RECONNECT_INITIAL_BACKOFF=1.0, so the first wait is 1.0.
        consumer = self._make_consumer()
        mocker.patch.object(consumer, '_run_session', side_effect=AMQPConnectionError('drop'))
        stop_event = threading.Event()

        timeouts: list[float] = []

        def fake_wait(timeout: float | None = None) -> bool:
            timeouts.append(timeout)  # type: ignore[arg-type]
            if len(timeouts) >= 2:
                stop_event.set()
            return stop_event.is_set()

        mocker.patch.object(stop_event, 'wait', side_effect=fake_wait)
        consumer.consume(stop_event=stop_event)

        assert timeouts[0] == 1.0
        assert timeouts[1] == 2.0

    def test_unrecoverable_error_propagates(self, mocker: MockerFixture) -> None:
        consumer = self._make_consumer()
        mocker.patch.object(consumer, '_run_session', side_effect=ValueError('fatal'))
        with pytest.raises(ValueError, match='fatal'):
            consumer.consume(stop_event=threading.Event())


class TestRunSession:
    def _patch_manager(self, mocker: MockerFixture, mock_connection: MagicMock) -> MagicMock:
        manager = MagicMock(name='ConnectionManager')
        manager.get_consumer_connection.return_value = mock_connection
        mocker.patch('django_rmq.consumer.get_connection_manager', return_value=manager)
        return manager

    def test_sets_qos_consumes_and_closes(
        self, mocker: MockerFixture, mock_connection: MagicMock, mock_channel: MagicMock
    ) -> None:
        self._patch_manager(mocker=mocker, mock_connection=mock_connection)
        consumer = Consumer(queue='orders', prefetch_count=5)
        consumer.handler(func=_noop_handler)
        stop_event = threading.Event()
        stop_event.set()  # skip the consume loop body entirely

        consumer._run_session(handler=_noop_handler, stop_event=stop_event)

        mock_channel.basic_qos.assert_called_once_with(prefetch_count=5)
        assert mock_channel.basic_consume.call_args.kwargs['queue'] == 'orders'
        mock_channel.stop_consuming.assert_called_once()
        mock_channel.close.assert_called_once()

    def test_processes_events_until_stop_event(
        self, mocker: MockerFixture, mock_connection: MagicMock, mock_channel: MagicMock
    ) -> None:
        self._patch_manager(mocker=mocker, mock_connection=mock_connection)
        consumer = Consumer(queue='orders')
        consumer.handler(func=_noop_handler)
        stop_event = threading.Event()

        def stop_after_first(time_limit: int) -> None:
            stop_event.set()

        mock_connection.process_data_events.side_effect = stop_after_first

        consumer._run_session(handler=_noop_handler, stop_event=stop_event)

        mock_connection.process_data_events.assert_called_once_with(time_limit=1)


class TestDeclareQueue:
    def test_string_queue_declared_durable(self, mock_channel: MagicMock) -> None:
        Consumer(queue='orders')._declare_queue(channel=mock_channel)
        mock_channel.queue_declare.assert_called_once_with(queue='orders', durable=True)

    def test_queue_config_declared_with_arguments(self, mock_channel: MagicMock) -> None:
        config = QueueConfig(
            name='orders',
            dead_letter_exchange='dlx-orders',
            dead_letter_routing_key='dlq-orders',
        )
        Consumer(queue=config)._declare_queue(channel=mock_channel)
        mock_channel.queue_declare.assert_called_once_with(
            queue='orders',
            durable=True,
            arguments={
                'x-dead-letter-exchange': 'dlx-orders',
                'x-dead-letter-routing-key': 'dlq-orders',
            },
        )

    def test_queue_config_with_queue_type_declared(self, mock_channel: MagicMock) -> None:
        config = QueueConfig(name='orders', queue_type=QueueType.QUORUM)
        Consumer(queue=config)._declare_queue(channel=mock_channel)
        mock_channel.queue_declare.assert_called_once_with(
            queue='orders',
            durable=True,
            arguments={'x-queue-type': 'quorum'},
        )


class TestDispatch:
    def test_closes_old_connections_and_calls_handler(self, mocker: MockerFixture, mock_channel: MagicMock) -> None:
        close = mocker.patch('django_rmq.consumer.close_old_connections')
        handler = MagicMock(name='handler')
        method = MagicMock(delivery_tag=7)
        props = MagicMock()

        Consumer(queue='orders')._dispatch(handler, mock_channel, method, props, b'body')

        close.assert_called_once()
        handler.assert_called_once_with(mock_channel, method, props, b'body')
        mock_channel.basic_nack.assert_not_called()

    def test_handler_exception_nacks_without_requeue(self, mocker: MockerFixture, mock_channel: MagicMock) -> None:
        mocker.patch('django_rmq.consumer.close_old_connections')
        handler = MagicMock(name='handler', side_effect=RuntimeError('handler boom'))
        method = MagicMock(delivery_tag=11)

        Consumer(queue='orders')._dispatch(handler, mock_channel, method, MagicMock(), b'body')

        mock_channel.basic_nack.assert_called_once_with(delivery_tag=11, requeue=False)
