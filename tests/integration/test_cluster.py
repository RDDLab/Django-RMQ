import threading
from typing import Any

import pytest
from pika.adapters.blocking_connection import BlockingChannel

from django_rmq.connections import RabbitMQConnectionManager
from django_rmq.consumer import Consumer
from django_rmq.producer import Producer
from tests.integration.conftest import MgmtApi, Names, NodeControl, build_config, poll


class TestClusterFailover:
    """
    End-to-end tests of client-side node failover against a real multi-node
    RabbitMQ cluster (see `.github/docker-compose.cluster.yml`). They prove the
    contract of the cluster feature: pika iterates the configured `NODES`
    sequence until one connects, and the existing reconnect logic re-runs that
    sequence so a client survives the loss of the node it was on.
    """

    @pytest.mark.integration
    def test_dead_node_in_list_is_skipped(
        self,
        configure_real_rmq,
        cluster_broker_params,
        broker_params: dict[str, Any],
        admin_channel: BlockingChannel,
        names: Names,
        run_consumer,
    ) -> None:
        """
        A single live broker plus an unreachable first node: pika must skip the
        dead node and complete a publish/consume roundtrip on the live one. Needs
        only one broker, so it runs in the regular single-broker integration job.
        """
        params: dict[str, Any] = cluster_broker_params(
            shuffle=False,
            endpoints=[('127.0.0.1', 1), (broker_params['HOST'], broker_params['PORT'])],
        )
        configure_real_rmq(connections={'default': params})
        admin_channel.queue_declare(queue=names.queue, durable=True)

        received: list[bytes] = []
        done: threading.Event = threading.Event()
        consumer: Consumer = Consumer(queue=names.queue)

        @consumer
        def handler(ch: BlockingChannel, method: Any, props: Any, body: bytes) -> None:
            received.append(body)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            done.set()

        run_consumer(consumer)
        Producer(queue=names.queue).publish(body=b'past-dead-node')

        assert done.wait(timeout=10), 'roundtrip did not complete past the dead node'
        assert received == [b'past-dead-node']

    @pytest.mark.integration
    @pytest.mark.cluster
    def test_shuffle_spreads_connections_across_nodes(
        self,
        require_cluster: None,
        cluster_broker_params,
        mgmt_api: MgmtApi,
    ) -> None:
        """
        With SHUFFLE_NODES enabled, many independent connections must land on more
        than one cluster node (each connection reshuffles the sequence, so the
        preferred node varies).
        """
        params: dict[str, Any] = cluster_broker_params(shuffle=True)
        attempts: int = 15

        before: set[str] = {c['name'] for c in mgmt_api.list_connections()}
        managers: list[RabbitMQConnectionManager] = []
        try:
            for _ in range(attempts):
                manager: RabbitMQConnectionManager = RabbitMQConnectionManager(config=build_config(params=params))
                manager.get_producer_connection()
                managers.append(manager)

            def _new_connections() -> list[dict[str, Any]]:
                fresh: list[dict[str, Any]] = [c for c in mgmt_api.list_connections() if c['name'] not in before]
                return fresh if len(fresh) >= attempts else []

            new: list[dict[str, Any]] = poll(_new_connections, timeout=10)
            assert new, 'cluster connections did not appear in the management API'
            nodes: set[str] = {c['node'] for c in new}
            assert len(nodes) >= 2, f'shuffle did not spread across nodes; all landed on {nodes}'
        finally:
            for manager in managers:
                manager.reset_producer_channel()

    @pytest.mark.integration
    @pytest.mark.cluster
    def test_failover_after_node_down(
        self,
        require_cluster: None,
        configure_real_rmq,
        cluster_broker_params,
        admin_channel: BlockingChannel,
        names: Names,
        run_consumer,
        node_control: NodeControl,
    ) -> None:
        """
        The headline scenario: a consumer and producer are pinned to the first
        node; that node is killed; both must fail over to a surviving node and
        deliver a message published after the kill. The queue is quorum (the
        cluster's default), so it survives the node loss.
        """
        params: dict[str, Any] = cluster_broker_params(shuffle=False)
        configure_real_rmq(connections={'default': params})
        # default_queue_type=quorum makes this a replicated, node-loss-tolerant queue.
        admin_channel.queue_declare(queue=names.queue, durable=True)

        received: list[bytes] = []
        got_message: threading.Event = threading.Event()
        consumer: Consumer = Consumer(queue=names.queue)

        @consumer
        def handler(ch: BlockingChannel, method: Any, props: Any, body: bytes) -> None:
            received.append(body)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            got_message.set()

        run_consumer(consumer)

        # Sanity: the client is up on the first node before we take it down.
        Producer(queue=names.queue).publish(body=b'before-failover')
        assert got_message.wait(timeout=10), 'consumer never received the pre-failover message'
        assert received == [b'before-failover']
        got_message.clear()

        # Kill the node the client is connected to (deterministic order -> node 0).
        node_control.kill(index=0)

        # Both the producer and the consumer must fail over to a surviving node.
        # We assert the end-to-end contract — a message can be published and
        # consumed again after the node dies — rather than the fate of one
        # specific message: right after the kill the quorum queue briefly elects
        # a new leader, so we keep publishing and waiting until the flow resumes.
        def _message_flows_again() -> bool:
            try:
                Producer(queue=names.queue).publish(body=b'after-failover')
            except Exception:
                return False
            return got_message.wait(timeout=1.0)

        assert poll(_message_flows_again, timeout=40), 'client did not recover after the node was killed'
        assert b'after-failover' in received
