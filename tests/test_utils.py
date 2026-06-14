import pytest
from django.core.exceptions import ImproperlyConfigured

from django_rmq.utils import resolve_alias


class TestResolveAlias:
    def test_single_entry_without_using_returns_it(self) -> None:
        assert resolve_alias(mapping={'default': 'value'}) == 'value'

    def test_single_entry_with_explicit_using(self) -> None:
        assert resolve_alias(mapping={'default': 'value'}, using='default') == 'value'

    def test_multiple_entries_with_using(self) -> None:
        mapping: dict[str, str] = {'default': 'a', 'analytics': 'b'}
        assert resolve_alias(mapping=mapping, using='analytics') == 'b'

    def test_multiple_entries_without_using_raises(self) -> None:
        mapping: dict[str, str] = {'default': 'a', 'analytics': 'b'}
        with pytest.raises(ImproperlyConfigured) as exc_info:
            resolve_alias(mapping=mapping)
        # The message lists the available aliases sorted, to guide the caller.
        assert 'analytics' in str(exc_info.value)
        assert 'default' in str(exc_info.value)

    def test_unknown_using_raises(self) -> None:
        with pytest.raises(ImproperlyConfigured, match='Unknown RabbitMQ alias'):
            resolve_alias(mapping={'default': 'a'}, using='missing')

    def test_none_mapping_raises_not_initialized(self) -> None:
        with pytest.raises(ImproperlyConfigured, match='not initialized'):
            resolve_alias(mapping=None)
