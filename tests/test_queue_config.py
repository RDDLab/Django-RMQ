from django_rmq.queues.queue_config import QueueConfig, QueueType


class TestQueueConfigStr:
    def test_str_returns_name(self) -> None:
        assert str(QueueConfig(name='orders')) == 'orders'


class TestQueueConfigPositionalArgs:
    def test_legacy_positional_dead_letter_args(self) -> None:
        config = QueueConfig('orders', True, 'dlx-orders', 'dlq-orders')
        assert config.dead_letter_exchange == 'dlx-orders'
        assert config.dead_letter_routing_key == 'dlq-orders'
        assert config.queue_type is None


class TestQueueConfigArguments:
    def test_arguments_none_when_no_settings(self) -> None:
        assert QueueConfig(name='orders').arguments is None

    def test_arguments_only_dead_letter(self) -> None:
        config = QueueConfig(
            name='orders',
            dead_letter_exchange='dlx-orders',
            dead_letter_routing_key='dlq-orders',
        )
        assert config.arguments == {
            'x-dead-letter-exchange': 'dlx-orders',
            'x-dead-letter-routing-key': 'dlq-orders',
        }

    def test_arguments_only_queue_type(self) -> None:
        config = QueueConfig(name='orders', queue_type=QueueType.QUORUM)
        assert config.arguments == {'x-queue-type': 'quorum'}

    def test_arguments_queue_type_and_dead_letter(self) -> None:
        config = QueueConfig(
            name='orders',
            queue_type=QueueType.QUORUM,
            dead_letter_exchange='dlx-orders',
            dead_letter_routing_key='dlq-orders',
        )
        assert config.arguments == {
            'x-queue-type': 'quorum',
            'x-dead-letter-exchange': 'dlx-orders',
            'x-dead-letter-routing-key': 'dlq-orders',
        }
