from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

from django_rmq.consumer import Consumer
from django_rmq.registries.registry import ConsumersRegistry, get_consumers_registry
from django_rmq.registries.setup_registry import SetupRegistry, get_setup_registry
from tests.conftest import DEFAULT_ALIAS_PARAMS, SECOND_ALIAS_PARAMS


class TestConsumersRegistry:
    def test_all_returns_registered_consumers(self) -> None:
        registry = ConsumersRegistry()
        consumer = Consumer(queue='orders')
        registry.register(consumer=consumer)
        assert registry.all() == [consumer]

    def test_all_returns_a_copy(self) -> None:
        registry = ConsumersRegistry()
        registry.register(consumer=Consumer(queue='orders'))
        snapshot = registry.all()
        snapshot.clear()
        # Mutating the returned list must not affect the registry.
        assert len(registry.all()) == 1


class TestSetupRegistry:
    def test_run_all_runs_in_registration_order(self) -> None:
        registry = SetupRegistry()
        calls: list[str] = []
        registry.register(fn=lambda channel: calls.append('first'))
        registry.register(fn=lambda channel: calls.append('second'))

        registry.run_all(channel=MagicMock())

        assert calls == ['first', 'second']

    def test_run_all_passes_channel(self) -> None:
        registry = SetupRegistry()
        received: list[Any] = []
        registry.register(fn=lambda channel: received.append(channel))
        channel = MagicMock()

        registry.run_all(channel=channel)

        assert received == [channel]


class TestRegistryAccessors:
    def test_accessors_resolve_per_alias(self, configure_rmq: Callable[[dict[str, dict[str, Any]]], None]) -> None:
        configure_rmq({'default': DEFAULT_ALIAS_PARAMS, 'analytics': SECOND_ALIAS_PARAMS})

        default_consumers = get_consumers_registry(using='default')
        analytics_consumers = get_consumers_registry(using='analytics')
        default_setup = get_setup_registry(using='default')
        analytics_setup = get_setup_registry(using='analytics')

        assert default_consumers is not analytics_consumers
        assert default_setup is not analytics_setup
