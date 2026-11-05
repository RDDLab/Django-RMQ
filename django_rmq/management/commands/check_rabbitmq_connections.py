import json
import logging
import os
import queue
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import (
    BaseCommand,
    CommandError,
    CommandParser,
)
from pika import BlockingConnection, ConnectionParameters

import django_rmq
from django_rmq.connections import get_connection_manager
from django_rmq.dto.healthcheck_config import HealthcheckConfig

logger = logging.getLogger('rabbitmq')

_LOGFMT_UNSAFE_CHARS: frozenset[str] = frozenset(' "=\\\t\n')


class OutputFormat(str, Enum):
    """
    Output formats supported by `check_rabbitmq_connections`.
    """

    JSON = 'json'
    TEXT = 'text'


@dataclass(frozen=True)
class AliasCheckResult:
    """
    Outcome of checking a single connection alias.

    :param alias: Connection alias from `RABBITMQ_CONNECTIONS`.
    :param ok: True if a connection was opened and closed successfully.
    :param seconds: Wall-clock time spent on the check (connect + close).
    :param node: `host:port` of the node that accepted the connection, if known.
    :param error: `<ExceptionType>: <message>` when the check failed.
    """

    alias: str
    ok: bool
    seconds: float
    node: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class NodeProbeResult:
    """
    Outcome of probing a single node of an alias.

    :param alias: Connection alias the node belongs to.
    :param node: `host:port` of the probed node.
    :param ok: True if a connection was opened and closed successfully.
    :param seconds: Seconds from the start of the check to the probe outcome.
    :param error: `<ExceptionType>: <message>` when the probe failed.
    """

    alias: str
    node: str
    ok: bool
    seconds: float
    error: str | None = None


class Command(BaseCommand):
    """
    Management command that verifies RabbitMQ connectivity.

    Every node of every checked alias is probed in parallel (open a connection,
    close it immediately) with the short timeouts from `RABBITMQ_HEALTHCHECK`.
    An alias is healthy as soon as any of its nodes answers, and failed once all
    of its nodes failed or the overall deadline expired. The alias's own
    `SOCKET_TIMEOUT`/`STACK_TIMEOUT` and `SHUFFLE_NODES` are not used: the
    probe time must not depend on node order. Intended as a healthcheck.
    """

    help = 'Healthcheck: ensure all (or a specific) RabbitMQ connection(s) are reachable.'

    # The probe runs every few seconds in a fresh process, so Django system checks
    # (which import the whole URLconf, among others) would be paid on every run.
    requires_system_checks: Literal['__all__'] | list[str] | tuple[str, ...] = ()

    def add_arguments(self, parser: CommandParser) -> None:
        """
        Registers the command-line arguments.
        """
        parser.add_argument(
            '--skip-checks',
            action='store_true',
            help='No-op, kept for backward compatibility: system checks are never run by this command.',
        )
        parser.add_argument(
            '--using',
            dest='using',
            default=None,
            help='Connection alias from RABBITMQ_CONNECTIONS to check. If omitted, checks every alias.',
        )
        parser.add_argument(
            '--format',
            dest='output_format',
            choices=[output_format.value for output_format in OutputFormat],
            default=OutputFormat.TEXT.value,
            help='Output format: logfmt-style key=value text (default) or one JSON object per line.',
        )
        parser.add_argument(
            '--timeout',
            dest='timeout',
            type=float,
            default=None,
            help='Overall deadline in seconds for the check. Defaults to RABBITMQ_HEALTHCHECK["DEADLINE"] (15).',
        )

    def handle(self, *args: Any, **kwargs: Any) -> None:
        """
        Checks connectivity for one or all aliases.

        :param kwargs: Parsed options; `using` selects a single alias, or checks
                       every alias when omitted; `output_format` selects the output
                       format; `timeout` overrides the configured deadline.
        :raises ImproperlyConfigured: If django_rmq has not been initialized.
        :raises CommandError: If `timeout` is not a positive number.
        :raises CommandError: If any checked alias is unreachable and the command
                              was invoked programmatically (`call_command`). From the
                              command line it exits with code 1 instead, so no
                              redundant `CommandError: ...` line is appended.
        """
        _source: str = 'check_rabbitmq_connections'
        using: str | None = kwargs.get('using')
        output_format: OutputFormat = OutputFormat(kwargs.get('output_format') or OutputFormat.TEXT.value)
        check_started_at: float = time.monotonic()
        startup_seconds: float | None = self._get_process_uptime()

        if django_rmq.connection_managers is None:
            raise ImproperlyConfigured('django_rmq is not initialized. Add "django_rmq" to INSTALLED_APPS.')

        config: HealthcheckConfig = django_rmq.healthcheck_config or HealthcheckConfig()
        timeout: float | None = kwargs.get('timeout')
        if timeout is not None and timeout <= 0:
            raise CommandError(f'--timeout must be a positive number of seconds, got {timeout!r}.')
        deadline: float = config.deadline if timeout is None else timeout

        if using is not None:
            aliases: list[str] = [using]
        else:
            aliases = list(django_rmq.connection_managers.keys())

        self._emit(line=self._render_startup(seconds=startup_seconds, output_format=output_format))

        results: list[AliasCheckResult] = []
        for result in self._iter_alias_results(aliases=aliases, config=config, deadline=deadline, source=_source):
            results.append(result)
            self._emit(line=self._render_check(result=result, output_format=output_format))

        total_seconds: float = (startup_seconds or 0.0) + (time.monotonic() - check_started_at)
        failed: list[str] = [result.alias for result in results if not result.ok]
        self._emit(
            line=self._render_summary(
                results=results,
                failed=failed,
                total_seconds=total_seconds,
                output_format=output_format,
            )
        )

        if output_format is OutputFormat.TEXT:
            # Error messages can be long; they go after the summary so that the
            # short per-alias lines and the summary are not pushed out of a
            # truncated probe output.
            for result in results:
                if not result.ok:
                    self._emit(line=self._render_error_detail(result=result))

        if failed:
            if getattr(self, '_called_from_command_line', False):
                # The summary line already says what is wrong; a CommandError here
                # would make Django append a redundant "CommandError: ..." line.
                sys.exit(1)
            raise CommandError(f'unhealthy: {", ".join(failed)}')

    def _emit(self, line: str) -> None:
        """
        Writes one output line to stdout and flushes it immediately.

        Flushing matters for healthchecks: stdout of a probe is a pipe (block
        buffered), and a probe killed on timeout never flushes its buffer.

        :param line: The fully rendered line, without a trailing newline.
        """
        self.stdout.write(line, style_func=lambda text: text)
        self.stdout.flush()

    @classmethod
    def _iter_alias_results(
        cls,
        aliases: list[str],
        config: HealthcheckConfig,
        deadline: float,
        source: str,
    ) -> Iterator[AliasCheckResult]:
        """
        Probes every node of every alias in parallel and yields alias outcomes as they are decided.

        Each node is probed in its own daemon thread, so a node that never answers
        neither delays the other aliases nor keeps the process alive after the
        command finishes. An alias is yielded as OK on its first successful node,
        as failed once all of its nodes failed, and as failed with a timeout when
        the deadline expires (in configuration order).

        :param aliases: Aliases to check.
        :param config: Healthcheck configuration (per-node timeouts).
        :param deadline: Overall budget in seconds for the whole check.
        :param source: Source identifier used for logging.
        :return: An iterator of alias outcomes, in the order they were decided.
        """
        started_at: float = time.monotonic()
        probe_results: queue.Queue[NodeProbeResult] = queue.Queue()
        pending: dict[str, list[str]] = {}
        errors: dict[str, list[str]] = {}

        # Resolve every alias first: an unknown alias must fail before any thread starts.
        node_parameters: dict[str, list[ConnectionParameters]] = {
            alias: get_connection_manager(using=alias).build_probe_parameters(
                socket_timeout=config.socket_timeout,
                stack_timeout=config.stack_timeout,
            )
            for alias in aliases
        }
        for alias, parameters in node_parameters.items():
            pending[alias] = []
            errors[alias] = []
            for params in parameters:
                node: str = f'{params.host}:{params.port}'
                pending[alias].append(node)
                threading.Thread(
                    target=cls._run_probe,
                    kwargs={
                        'alias': alias,
                        'node': node,
                        'params': params,
                        'started_at': started_at,
                        'results': probe_results,
                    },
                    name=f'rmq-healthcheck-{alias}-{node}',
                    daemon=True,
                ).start()

        while pending:
            remaining: float = deadline - (time.monotonic() - started_at)
            if remaining <= 0:
                break
            try:
                probe: NodeProbeResult = probe_results.get(timeout=remaining)
            except queue.Empty:
                break
            if probe.alias not in pending:
                # The alias was already decided by another node.
                continue

            if probe.ok:
                del pending[probe.alias]
                yield AliasCheckResult(alias=probe.alias, ok=True, seconds=probe.seconds, node=probe.node)
                continue

            errors[probe.alias].append(f'{probe.node} {probe.error}')
            pending[probe.alias].remove(probe.node)
            if not pending[probe.alias]:
                del pending[probe.alias]
                yield cls._failed_result(
                    alias=probe.alias,
                    seconds=probe.seconds,
                    error='; '.join(errors[probe.alias]),
                    source=source,
                )

        seconds: float = time.monotonic() - started_at
        for alias, unanswered in pending.items():
            details: list[str] = [*errors[alias], *(f'{node} no answer' for node in unanswered)]
            yield cls._failed_result(
                alias=alias,
                seconds=seconds,
                error='; '.join([f'TimeoutError: no node answered within {deadline:g}s', *details]),
                source=source,
            )

    @classmethod
    def _run_probe(
        cls,
        alias: str,
        node: str,
        params: ConnectionParameters,
        started_at: float,
        results: 'queue.Queue[NodeProbeResult]',
    ) -> None:
        """
        Probes a single node and puts the outcome into `results` (thread target).

        Any exception is reported as a failed probe: an exception escaping the
        thread would leave the alias waiting until the deadline.

        :param alias: Connection alias the node belongs to.
        :param node: `host:port` of the node.
        :param params: Connection parameters of this node only.
        :param started_at: `time.monotonic()` at the start of the check.
        :param results: Queue that collects probe outcomes.
        """
        _source: str = 'check_rabbitmq_connections'
        try:
            cls._probe_node(params=params)
        except Exception as exc:
            seconds: float = time.monotonic() - started_at
            error: str = cls._describe_error(exc=exc)
            logger.warning(
                {
                    'source': _source,
                    'message': 'RabbitMQ node probe failed',
                    'data': {'alias': alias, 'node': node, 'error': error, 'seconds': round(seconds, 3)},
                }
            )
            results.put(NodeProbeResult(alias=alias, node=node, ok=False, seconds=seconds, error=error))
            return

        seconds = time.monotonic() - started_at
        logger.debug(
            {
                'source': _source,
                'message': 'RabbitMQ node probe OK',
                'data': {'alias': alias, 'node': node, 'seconds': round(seconds, 3)},
            }
        )
        results.put(NodeProbeResult(alias=alias, node=node, ok=True, seconds=seconds))

    @classmethod
    def _probe_node(cls, params: ConnectionParameters) -> None:
        """
        Opens a connection to a single node and closes it immediately.

        :param params: Connection parameters of the node.
        :raises Exception: Whatever pika raises when the node is unreachable.
        """
        connection: BlockingConnection = BlockingConnection(parameters=params)
        connection.close()

    @classmethod
    def _failed_result(cls, alias: str, seconds: float, error: str, source: str) -> AliasCheckResult:
        """
        Builds a failed alias outcome and logs it.

        :param alias: The failed alias.
        :param seconds: Seconds from the start of the check to the failure.
        :param error: Combined error description of the alias nodes.
        :param source: Source identifier used for logging.
        :return: The failed alias outcome.
        """
        logger.warning(
            {
                'source': source,
                'message': 'RabbitMQ connection failed',
                'data': {'alias': alias, 'error': error, 'seconds': round(seconds, 3)},
            }
        )
        return AliasCheckResult(alias=alias, ok=False, seconds=seconds, error=error)

    @classmethod
    def _describe_error(cls, exc: BaseException) -> str:
        """
        Renders an exception as `<ExceptionType>: <message>`.

        Several pika exceptions stringify to an empty string, so `repr()` of the
        arguments is used as a fallback to never print a bare type name.

        :param exc: The exception raised while checking an alias.
        :return: A single-line, human-readable error description.
        """
        message: str = str(exc) or (repr(exc.args) if exc.args else '')
        description: str = f'{type(exc).__name__}: {message}' if message else type(exc).__name__
        return ' '.join(description.split())

    @classmethod
    def _get_process_uptime(cls) -> float | None:
        """
        Returns seconds elapsed since the current process started.

        Linux only: reads the process start time (field 22 of `/proc/self/stat`,
        in clock ticks since boot) and the system uptime from `/proc/uptime`.

        :return: Seconds since process start, or None where `/proc` is unavailable.
        """
        try:
            with open(file='/proc/self/stat', encoding='utf-8') as stat_file:
                stat: str = stat_file.read()
            with open(file='/proc/uptime', encoding='utf-8') as uptime_file:
                system_uptime: float = float(uptime_file.read().split()[0])
            # `comm` (field 2) may contain spaces and parentheses, so split after
            # its closing parenthesis: the remainder starts at field 3.
            fields_from_state: list[str] = stat.rsplit(')', 1)[1].split()
            start_ticks: int = int(fields_from_state[22 - 3])
            clock_ticks_per_second: int = os.sysconf('SC_CLK_TCK')
        except (OSError, ValueError, IndexError):
            return None
        return max(system_uptime - start_ticks / clock_ticks_per_second, 0.0)

    @classmethod
    def _render_startup(cls, seconds: float | None, output_format: OutputFormat) -> str:
        """
        Renders the `startup` event.

        :param seconds: Seconds from process start to the beginning of the check, or None if unknown.
        :param output_format: Target output format.
        :return: The rendered line.
        """
        if output_format is OutputFormat.JSON:
            return cls._to_json(payload={'event': 'startup', 'seconds': cls._round(seconds=seconds)})
        return cls._to_logfmt(head=None, pairs={'startup': cls._format_seconds(seconds=seconds)})

    @classmethod
    def _render_check(cls, result: AliasCheckResult, output_format: OutputFormat) -> str:
        """
        Renders the `check` event of a single alias.

        :param result: The alias check outcome.
        :param output_format: Target output format.
        :return: The rendered line.
        """
        if output_format is OutputFormat.JSON:
            payload: dict[str, Any] = {
                'event': 'check',
                'status': 'ok' if result.ok else 'fail',
                'alias': result.alias,
                'seconds': cls._round(seconds=result.seconds),
            }
            if result.ok:
                payload['node'] = result.node
            else:
                payload['error'] = result.error
            return cls._to_json(payload=payload)

        if result.ok:
            return cls._to_logfmt(
                head='OK',
                pairs={
                    'alias': result.alias,
                    'node': result.node or 'unknown',
                    'connect': cls._format_seconds(seconds=result.seconds),
                },
            )
        return cls._to_logfmt(
            head='FAIL',
            pairs={
                'alias': result.alias,
                'took': cls._format_seconds(seconds=result.seconds),
            },
        )

    @classmethod
    def _render_error_detail(cls, result: AliasCheckResult) -> str:
        """
        Renders the text-format `ERROR` line with the error of a failed alias.

        :param result: The failed alias check outcome.
        :return: The rendered line.
        """
        return cls._to_logfmt(
            head='ERROR',
            pairs={
                'alias': result.alias,
                'error': result.error or 'unknown',
            },
        )

    @classmethod
    def _render_summary(
        cls,
        results: list[AliasCheckResult],
        failed: list[str],
        total_seconds: float,
        output_format: OutputFormat,
    ) -> str:
        """
        Renders the final `summary` event.

        :param results: Outcomes of all checked aliases.
        :param failed: Aliases that failed the check.
        :param total_seconds: Seconds since process start (or since the check
                              started, when the process start time is unknown).
        :param output_format: Target output format.
        :return: The rendered line.
        """
        healthy_count: int = len(results) - len(failed)
        if output_format is OutputFormat.JSON:
            return cls._to_json(
                payload={
                    'event': 'summary',
                    'status': 'unhealthy' if failed else 'healthy',
                    'healthy': healthy_count,
                    'total': len(results),
                    'failed': failed,
                    'seconds': cls._round(seconds=total_seconds),
                }
            )

        pairs: dict[str, str] = {}
        if failed:
            pairs['failed'] = ','.join(failed)
        pairs['aliases'] = f'{healthy_count}/{len(results)}'
        pairs['total'] = cls._format_seconds(seconds=total_seconds)
        return cls._to_logfmt(head='UNHEALTHY' if failed else 'HEALTHY', pairs=pairs)

    @classmethod
    def _to_json(cls, payload: dict[str, Any]) -> str:
        """
        Serializes an event as a single-line JSON object.

        :param payload: The event fields.
        :return: The JSON line.
        """
        return json.dumps(obj=payload, ensure_ascii=False)

    @classmethod
    def _to_logfmt(cls, head: str | None, pairs: dict[str, str]) -> str:
        """
        Renders an event as `HEAD key=value key="quoted value"`.

        :param head: Optional leading status word (e.g. `OK`, `FAIL`).
        :param pairs: Ordered key/value pairs.
        :return: The logfmt-style line.
        """
        parts: list[str] = [head] if head is not None else []
        parts.extend(f'{key}={cls._quote_logfmt_value(value=value)}' for key, value in pairs.items())
        return ' '.join(parts)

    @classmethod
    def _quote_logfmt_value(cls, value: str) -> str:
        """
        Quotes a logfmt value when it is empty or contains unsafe characters.

        :param value: The raw value.
        :return: The value as is, or double-quoted with `\\` and `"` escaped.
        """
        if value and not _LOGFMT_UNSAFE_CHARS.intersection(value):
            return value
        escaped: str = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'

    @classmethod
    def _format_seconds(cls, seconds: float | None) -> str:
        """
        Formats a duration for text output.

        :param seconds: Duration in seconds, or None if unknown.
        :return: E.g. `8.71s`, or `unknown`.
        """
        return 'unknown' if seconds is None else f'{seconds:.2f}s'

    @classmethod
    def _round(cls, seconds: float | None) -> float | None:
        """
        Rounds a duration for JSON output.

        :param seconds: Duration in seconds, or None if unknown.
        :return: The duration rounded to milliseconds, or None.
        """
        return None if seconds is None else round(seconds, 3)
