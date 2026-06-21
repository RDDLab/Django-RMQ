import os

import django


def _main() -> None:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
    django.setup()

    from django.core.management import call_command

    import django_rmq
    from django_rmq.connections import RabbitMQConnectionManager
    from django_rmq.consumer import Consumer
    from django_rmq.dto.rabbitmq_config import RabbitMQConfig
    from django_rmq.registries.registry import ConsumersRegistry, get_consumers_registry
    from django_rmq.registries.setup_registry import SetupRegistry

    config: RabbitMQConfig = RabbitMQConfig(
        host=os.environ.get('RMQ_HOST', 'localhost'),
        port=int(os.environ.get('RMQ_PORT', '5672')),
        virtual_host=os.environ.get('RMQ_VHOST', '/'),
        user=os.environ.get('RMQ_USER', 'guest'),
        password=os.environ.get('RMQ_PASSWORD', 'guest'),
        heartbeat=int(os.environ.get('RMQ_HEARTBEAT', '30')),
        blocked_connection_timeout=300,
        reconnect_initial_backoff=0.2,
        reconnect_max_backoff=1.0,
    )
    django_rmq.connection_managers = {'default': RabbitMQConnectionManager(config=config)}
    django_rmq.setup_registries = {'default': SetupRegistry()}
    django_rmq.consumers_registries = {'default': ConsumersRegistry()}

    output_path: str = os.environ['IT_OUTPUT']
    consumer: Consumer = Consumer(queue=os.environ['IT_QUEUE'])

    @consumer
    def handler(ch, method, props, body: bytes) -> None:
        with open(output_path, 'ab') as output_file:
            output_file.write(body + b'\n')
        ch.basic_ack(delivery_tag=method.delivery_tag)

    get_consumers_registry().register(consumer=consumer)
    call_command('start_consumers')


if __name__ == '__main__':
    _main()
