from collections.abc import Callable
from enum import Enum

from django.utils.termcolors import make_style


class CommandStyle(Enum):
    """
    Predefined terminal styles for management command output.

    Each member declares its `make_style` configuration (display options and an
    optional foreground color); the corresponding style callable is built once in
    `__init__`. Call `apply` to render a string in that style, e.g.
    `CommandStyle.BOLD_GREEN.apply(text='django-rmq 0.0.1')`.
    """

    BOLD = (('bold',), None)
    BOLD_GREEN = (('bold',), 'green')
    BOLD_CYAN = (('bold',), 'cyan')

    def __init__(self, opts: tuple[str, ...], fg: str | None) -> None:
        """
        Builds the style callable for this member.

        :param opts: Display options passed to `make_style` (e.g. `('bold',)`).
        :param fg: Foreground color name, or None to leave the color unset.
        """
        style_kwargs: dict[str, object] = {'opts': opts}
        if fg is not None:
            style_kwargs['fg'] = fg
        self._style: Callable[[str], str] = make_style(**style_kwargs)

    def apply(self, text: str) -> str:
        """
        Renders the given text in this style.

        :param text: The text to style.
        :return: The text wrapped in the terminal escape codes for this style,
                 or the unchanged text when color output is disabled.
        """
        return self._style(text)
