import contextlib
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from base64 import b64encode
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from json import dumps, loads
from typing import Any, NamedTuple
from urllib.parse import quote

import pytest
from pika import BlockingConnection, ConnectionParameters, PlainCredentials
from pika.adapters.blocking_connection import BlockingChannel

import django_rmq
from django_rmq.apps import RabbitMQAppConfig
from django_rmq.connections import RabbitMQConnectionManager
from django_rmq.dto.rabbitmq_config import RabbitMQConfig
from django_rmq.registries.registry import ConsumersRegistry
from django_rmq.registries.setup_registry import SetupRegistry


def _env(name: str, default: str) -> str:
    """
    Reads an `RMQ_*` environment variable, falling back to a local-broker default.
    """
    return os.environ.get(name, default)


def connection_parameters(params: dict[str, Any]) -> ConnectionParameters:
    """
    Builds pika ConnectionParameters from a RABBITMQ_CONNECTIONS-style alias dict.
    """
    return ConnectionParameters(
        host=params['HOST'],
        port=params['PORT'],
        virtual_host=params['VIRTUAL_HOST'],
        credentials=PlainCredentials(username=params['USER'], password=params['PASSWORD']),
        heartbeat=params['HEARTBEAT'],
        blocked_connection_timeout=params['BLOCKED_CONNECTION_TIMEOUT'],
    )


def build_config(params: dict[str, Any]) -> RabbitMQConfig:
    """
    Builds a RabbitMQConfig from a RABBITMQ_CONNECTIONS-style alias dict,
    reusing the app's own normalization so integration tests exercise it too.
    """
    return RabbitMQAppConfig._build_config(alias='integration', params=params)


def poll(predicate: Callable[[], Any], timeout: float = 10.0, interval: float = 0.1) -> Any:
    """
    Polls `predicate` until it returns a truthy value or `timeout` elapses.

    :return: The last value returned by `predicate` (truthy on success, falsy on
             timeout) so callers can assert on it directly.
    """
    deadline: float = time.monotonic() + timeout
    value: Any = predicate()
    while not value and time.monotonic() < deadline:
        time.sleep(interval)
        value = predicate()
    return value


@dataclass
class Names:
    """
    Per-test, collision-free topology names. The `dlq`/`dlx` follow the library's
    `dlq-`/`dlx-` naming conventions so the tests double as documentation.
    """

    suffix: str
    queue: str
    dlq: str
    dlx: str
    exchange: str

    @property
    def all_queues(self) -> list[str]:
        return [self.queue, self.dlq]

    @property
    def all_exchanges(self) -> list[str]:
        return [self.dlx, self.exchange]


class MgmtApi:
    """
    Tiny RabbitMQ Management HTTP API client built on stdlib `urllib` (no extra
    dependency). Scoped to a single vhost for queue lookups; connection
    operations are vhost-agnostic.
    """

    def __init__(self, base_url: str, user: str, password: str, vhost: str) -> None:
        self._base_url: str = base_url.rstrip('/')
        self._user: str = user
        self._password: str = password
        self._vhost: str = vhost
        token: str = b64encode(f'{user}:{password}'.encode()).decode()
        self._auth_header: str = f'Basic {token}'

    def for_vhost(self, vhost: str) -> 'MgmtApi':
        """
        Returns a client with the same host/credentials, scoped to another vhost.
        """
        return MgmtApi(base_url=self._base_url, user=self._user, password=self._password, vhost=vhost)

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        url: str = f'{self._base_url}{path}'
        data: bytes | None = dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url=url, method=method, data=data)
        request.add_header('Authorization', self._auth_header)
        request.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload: bytes = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        return loads(payload) if payload else None

    def list_connections(self) -> list[dict[str, Any]]:
        """
        Returns all open connections on the broker (across vhosts).
        """
        return self._request(method='GET', path='/api/connections') or []

    def kill_connection(self, name: str) -> None:
        """
        Force-closes a connection by its broker-assigned name.
        """
        self._request(method='DELETE', path=f'/api/connections/{quote(name, safe="")}')

    def queue(self, name: str) -> dict[str, Any] | None:
        """
        Returns the queue's Management API record in this vhost, or None if absent.
        """
        vhost: str = quote(self._vhost, safe='')
        return self._request(method='GET', path=f'/api/queues/{vhost}/{quote(name, safe="")}')

    def _queue_stat(self, name: str, field: str) -> int:
        """
        Returns an integer field from a queue's record (0 if the queue is missing).
        """
        info: dict[str, Any] | None = self.queue(name=name)
        return int(info.get(field, 0)) if info else 0

    def messages(self, name: str) -> int:
        """
        Returns the ready message count for a queue (0 if the queue is missing).
        """
        return self._queue_stat(name=name, field='messages_ready')

    def messages_unacknowledged(self, name: str) -> int:
        """
        Returns the unacknowledged message count for a queue (0 if missing).
        """
        return self._queue_stat(name=name, field='messages_unacknowledged')

    def consumer_count(self, name: str) -> int:
        """
        Returns the number of consumers attached to a queue (0 if missing).
        """
        return self._queue_stat(name=name, field='consumers')

    def exchange_exists(self, name: str) -> bool:
        """
        Returns whether an exchange exists in this vhost.
        """
        vhost: str = quote(self._vhost, safe='')
        return self._request(method='GET', path=f'/api/exchanges/{vhost}/{quote(name, safe="")}') is not None

    def create_vhost(self, name: str, user: str) -> None:
        """
        Creates a vhost and grants `user` full permissions on it.
        """
        self._request(method='PUT', path=f'/api/vhosts/{quote(name, safe="")}')
        self._request(
            method='PUT',
            path=f'/api/permissions/{quote(name, safe="")}/{quote(user, safe="")}',
            body={'configure': '.*', 'write': '.*', 'read': '.*'},
        )

    def delete_vhost(self, name: str) -> None:
        """
        Deletes a vhost (idempotent — 404 is swallowed).
        """
        self._request(method='DELETE', path=f'/api/vhosts/{quote(name, safe="")}')


@pytest.fixture(scope='session')
def broker_params() -> dict[str, Any]:
    """
    RABBITMQ_CONNECTIONS-style alias dict from the environment.

    Heartbeat and reconnect backoff are intentionally small so reconnect tests
    finish quickly; everything else mirrors a production alias entry.
    """
    return {
        'HOST': _env('RMQ_HOST', 'localhost'),
        'PORT': int(_env('RMQ_PORT', '5672')),
        'VIRTUAL_HOST': _env('RMQ_VHOST', '/'),
        'USER': _env('RMQ_USER', 'guest'),
        'PASSWORD': _env('RMQ_PASSWORD', 'guest'),
        'HEARTBEAT': int(_env('RMQ_HEARTBEAT', '30')),
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 0.2,
        'RECONNECT_MAX_BACKOFF': 1.0,
    }


@pytest.fixture(scope='session')
def mgmt_api(broker_params: dict[str, Any]) -> MgmtApi:
    """
    Management API client bound to the broker's host and the test vhost.
    """
    host: str = broker_params['HOST']
    port: str = _env('RMQ_MGMT_PORT', '15672')
    return MgmtApi(
        base_url=f'http://{host}:{port}',
        user=broker_params['USER'],
        password=broker_params['PASSWORD'],
        vhost=broker_params['VIRTUAL_HOST'],
    )


@pytest.fixture(scope='session', autouse=True)
def require_broker(broker_params: dict[str, Any]) -> None:
    """
    Fails the session if the broker is not reachable within the startup window.
    """
    parameters: ConnectionParameters = connection_parameters(params=broker_params)
    deadline: float = time.monotonic() + 15
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            connection: BlockingConnection = BlockingConnection(parameters=parameters)
            connection.close()
            return
        except Exception as exc:  # any dial failure means "not ready yet"
            last_error = exc
            time.sleep(0.5)
    pytest.fail(f'RabbitMQ broker not reachable at {broker_params["HOST"]}:{broker_params["PORT"]}: {last_error}')


@pytest.fixture
def configure_real_rmq(broker_params: dict[str, Any]) -> Iterator[Callable[..., dict[str, RabbitMQConnectionManager]]]:
    """
    Installs *real* (non-mocked) connection managers and empty registries on the
    `django_rmq` module, mirroring `AppConfig.ready()` but pointed at the live
    broker. Defaults to a single `default` alias; pass a mapping for multi-alias
    tests. Producer channels opened during the test are closed on teardown
    (`reset_rmq_state` from the parent conftest rebuilds the mocked defaults).
    """
    created: list[RabbitMQConnectionManager] = []

    def _configure(connections: dict[str, dict[str, Any]] | None = None) -> dict[str, RabbitMQConnectionManager]:
        connections = connections if connections is not None else {'default': broker_params}
        managers: dict[str, RabbitMQConnectionManager] = {
            alias: RabbitMQConnectionManager(config=build_config(params=params))
            for alias, params in connections.items()
        }
        django_rmq.connection_managers = managers
        django_rmq.setup_registries = {alias: SetupRegistry() for alias in connections}
        django_rmq.consumers_registries = {alias: ConsumersRegistry() for alias in connections}
        created.extend(managers.values())
        return managers

    yield _configure

    for manager in created:
        with contextlib.suppress(Exception):
            manager.reset_producer_channel()


@pytest.fixture
def names() -> Names:
    """
    Returns collision-free topology names for one test.
    """
    suffix: str = uuid.uuid4().hex[:8]
    return Names(
        suffix=suffix,
        queue=f'it-q-{suffix}',
        dlq=f'dlq-it-{suffix}',
        dlx=f'dlx-it-{suffix}',
        exchange=f'it-x-{suffix}',
    )


@pytest.fixture
def admin_channel(broker_params: dict[str, Any], names: Names) -> Iterator[BlockingChannel]:
    """
    A dedicated admin connection/channel for declaring, asserting, and cleaning
    up topology — kept separate from the channels the code under test uses.

    On teardown every queue and exchange in `names` is deleted (best-effort),
    so a shared broker stays clean across tests.
    """
    connection: BlockingConnection = BlockingConnection(parameters=connection_parameters(params=broker_params))
    channel: BlockingChannel = connection.channel()
    yield channel

    cleanup_connection: BlockingConnection = BlockingConnection(parameters=connection_parameters(params=broker_params))
    cleanup_channel: BlockingChannel = cleanup_connection.channel()
    # A failed delete (e.g. 404) closes the channel, so a fresh one is opened
    # before the next attempt.
    for queue in names.all_queues:
        try:
            cleanup_channel.queue_delete(queue=queue)
        except Exception:  # best-effort cleanup on a shared broker
            cleanup_channel = cleanup_connection.channel()
    for exchange in names.all_exchanges:
        try:
            cleanup_channel.exchange_delete(exchange=exchange)
        except Exception:  # best-effort cleanup on a shared broker
            cleanup_channel = cleanup_connection.channel()
    for conn in (connection, cleanup_connection):
        with contextlib.suppress(Exception):
            conn.close()


class RunningConsumer(NamedTuple):
    """
    Handles to a consumer running in a daemon thread: the thread itself and the
    `stop_event` that ends its consume loop.
    """

    thread: threading.Thread
    stop_event: threading.Event


@pytest.fixture
def run_consumer() -> Iterator[Callable[[Any], RunningConsumer]]:
    """
    Starts `consumer.consume()` in a daemon thread and returns its thread and
    `stop_event` so a test can stop it early. All started consumers are stopped
    and joined on teardown.
    """
    running: list[RunningConsumer] = []

    def _run(consumer: Any) -> RunningConsumer:
        stop_event: threading.Event = threading.Event()
        thread: threading.Thread = threading.Thread(
            target=consumer.consume,
            kwargs={'stop_event': stop_event},
            name=f'it-consumer-{consumer.queue}',
            daemon=True,
        )
        thread.start()
        handle: RunningConsumer = RunningConsumer(thread=thread, stop_event=stop_event)
        running.append(handle)
        return handle

    yield _run

    for handle in running:
        handle.stop_event.set()
    for handle in running:
        handle.thread.join(timeout=10)


# --------------------------------------------------------------------------- #
# Cluster fixtures                                                            #
#                                                                             #
# These target the three-node cluster from                                    #
# `.github/docker-compose.cluster.yml`. They are used only by tests marked    #
# `cluster` and auto-skip when a real cluster is not reachable, so a          #
# single-broker environment stays green.                                      #
# --------------------------------------------------------------------------- #


def _amqp_reachable(host: str, port: int, *, params: dict[str, Any]) -> bool:
    """
    Returns True if an AMQP connection to host:port can be opened right now.
    """
    node_params: dict[str, Any] = {**params, 'HOST': host, 'PORT': port}
    try:
        connection: BlockingConnection = BlockingConnection(parameters=connection_parameters(params=node_params))
        connection.close()
    except Exception:  # any dial failure means "not reachable"
        return False
    return True


@pytest.fixture(scope='session')
def cluster_endpoints() -> list[tuple[str, int]]:
    """
    Parses the cluster's AMQP endpoints from `RMQ_CLUSTER_NODES`.

    Format: comma-separated `host:port` pairs. Defaults to the three host ports
    published by `.github/docker-compose.cluster.yml`.
    """
    raw: str = _env('RMQ_CLUSTER_NODES', 'localhost:5672,localhost:5673,localhost:5674')
    endpoints: list[tuple[str, int]] = []
    for item in raw.split(','):
        host, _, port = item.strip().partition(':')
        endpoints.append((host, int(port)))
    return endpoints


@pytest.fixture(scope='session')
def cluster_containers() -> list[str]:
    """
    Docker container names for the cluster nodes, index-aligned with
    `cluster_endpoints`. Overridable via `RMQ_CLUSTER_CONTAINERS`.
    """
    raw: str = _env(
        'RMQ_CLUSTER_CONTAINERS',
        'django-rmq-cluster-rabbit1,django-rmq-cluster-rabbit2,django-rmq-cluster-rabbit3',
    )
    return [name.strip() for name in raw.split(',')]


@pytest.fixture(scope='session')
def cluster_broker_params(
    broker_params: dict[str, Any],
    cluster_endpoints: list[tuple[str, int]],
) -> Callable[..., dict[str, Any]]:
    """
    Returns a builder for a `RABBITMQ_CONNECTIONS`-style alias dict whose `NODES`
    point at the whole cluster. Credentials/vhost/timeouts are inherited from
    `broker_params`; `HOST`/`PORT` are replaced by the multi-node `NODES` list.
    """

    def _build(shuffle: bool = False, endpoints: list[tuple[str, int]] | None = None) -> dict[str, Any]:
        nodes: list[tuple[str, int]] = endpoints if endpoints is not None else cluster_endpoints
        params: dict[str, Any] = {key: value for key, value in broker_params.items() if key not in ('HOST', 'PORT')}
        params['NODES'] = [{'HOST': host, 'PORT': port} for host, port in nodes]
        params['SHUFFLE_NODES'] = shuffle
        return params

    return _build


@pytest.fixture(scope='session')
def require_cluster(
    broker_params: dict[str, Any],
    cluster_endpoints: list[tuple[str, int]],
) -> None:
    """
    Skips the test session's cluster tests unless at least two cluster nodes are
    reachable (a single broker is not a cluster).
    """
    reachable: int = sum(
        1 for host, port in cluster_endpoints if _amqp_reachable(host=host, port=port, params=broker_params)
    )
    if reachable < 2:
        pytest.skip(f'RabbitMQ cluster not available (only {reachable} node(s) reachable)')


class NodeControl:
    """
    Kills and restarts cluster nodes by their Docker container name so a test can
    simulate a node going down. `kill` uses `docker kill` (immediate, like a
    crash); `start` brings the same container back (its filesystem, hence the
    quorum queue data, is preserved across the restart).
    """

    def __init__(self, containers: list[str], endpoints: list[tuple[str, int]], params: dict[str, Any]) -> None:
        self._containers: list[str] = containers
        self._endpoints: list[tuple[str, int]] = endpoints
        self._params: dict[str, Any] = params

    @classmethod
    def _docker(cls, *args: str) -> None:
        subprocess.run(['docker', *args], check=True, capture_output=True)

    def kill(self, index: int) -> None:
        """
        Force-stops the node at `index` and waits until its AMQP port is closed.
        """
        self._docker('kill', self._containers[index])
        host, port = self._endpoints[index]
        assert poll(
            lambda: not _amqp_reachable(host=host, port=port, params=self._params),
            timeout=15,
        ), f'node {self._containers[index]} still reachable after kill'

    def start(self, index: int) -> None:
        """
        Starts the node at `index` and waits until its AMQP port accepts connections.
        """
        self._docker('start', self._containers[index])
        host, port = self._endpoints[index]
        assert poll(
            lambda: _amqp_reachable(host=host, port=port, params=self._params),
            timeout=30,
        ), f'node {self._containers[index]} not reachable after start'


@pytest.fixture
def node_control(
    broker_params: dict[str, Any],
    cluster_endpoints: list[tuple[str, int]],
    cluster_containers: list[str],
) -> Iterator[NodeControl]:
    """
    Provides a NodeControl for killing/restarting cluster nodes. Skips the test
    if Docker is unavailable or a container is missing. On teardown every node is
    started again and awaited healthy — this runs before topology cleanup so
    deletes go against a live cluster.
    """
    if shutil.which('docker') is None:
        pytest.skip('docker CLI not available for node control')

    control: NodeControl = NodeControl(
        containers=cluster_containers,
        endpoints=cluster_endpoints,
        params=broker_params,
    )
    for name in cluster_containers:
        result = subprocess.run(['docker', 'inspect', name], capture_output=True, check=False)
        if result.returncode != 0:
            pytest.skip(f'cluster container {name!r} not found (is the cluster compose up?)')

    yield control

    # Best-effort: bring every node back so a killed node never leaks into the
    # next test.
    for index in range(len(cluster_containers)):
        with contextlib.suppress(Exception):
            control.start(index)
