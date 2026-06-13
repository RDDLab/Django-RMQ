import platform
import shutil
from importlib.metadata import (
    PackageNotFoundError,
    metadata,
)

from django.core.management.base import BaseCommand

from django_rmq.management.ascii_art import ASCII_ART
from django_rmq.management.enums.command_styles import CommandStyle

DISTRIBUTION_NAME: str = 'django-rmq'
LIBRARY_NAME: str = 'Django-RMQ'
GITHUB_ORG_URL: str = 'https://github.com/RDDLab'


class RDDBaseCommand(BaseCommand):
    """
    Base command for all django_rmq management commands.

    Provides the shared startup banner (ASCII art, library name and version,
    running Python version and GitHub organization link) and a terminal-width
    aware separator, so every command renders a consistent header.
    """

    @classmethod
    def _separator(cls) -> str:
        """
        Builds a horizontal separator spanning the full terminal width.

        :return: A line of box-drawing characters as wide as the terminal.
        """
        width: int = shutil.get_terminal_size(fallback=(64, 24)).columns
        return '─' * width

    @classmethod
    def _get_distribution_metadata(cls) -> tuple[str, str]:
        """
        Resolves the library name and version from the installed package metadata.

        Both values originate from the `[project]` table of pyproject.toml
        (`name` and `version`).

        :return: A `(name, version)` tuple, falling back to the distribution name
                 and 'unknown' if the metadata cannot be resolved.
        """
        try:
            distribution_metadata = metadata(distribution_name=DISTRIBUTION_NAME)
        except PackageNotFoundError:
            return DISTRIBUTION_NAME, 'unknown'

        return distribution_metadata['Name'], distribution_metadata['Version']

    def _print_banner(self) -> None:
        """
        Prints the startup banner: ASCII art, then an aligned table of the library
        name and version, the running Python version and the GitHub organization
        link.
        """
        _, library_version = self._get_distribution_metadata()

        rows: list[tuple[str, str, CommandStyle]] = [
            (LIBRARY_NAME, library_version, CommandStyle.BOLD_GREEN),
            ('Python', platform.python_version(), CommandStyle.BOLD),
            ('GitHub', GITHUB_ORG_URL, CommandStyle.BOLD_CYAN),
        ]
        label_width: int = max(len(label) for label, _, _ in rows) + len(':')

        self.stdout.write(self.style.SUCCESS(ASCII_ART))
        for label, value, style in rows:
            self.stdout.write(style.apply(text=f'{label + ":":<{label_width}}   {value}'))
        self.stdout.write(self.style.SUCCESS(self._separator()))
