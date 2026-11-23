"""The loading screen: a small page the window shows before the app is ready."""

import base64
import html
import logging
from importlib import resources
from pathlib import Path
from string import Template

from cornea.core.config import Colour, Html, Loading, Window
from cornea.core.window.theme import system_prefers_dark

logger = logging.getLogger(__name__)

_IMAGE_TYPES = {
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

# No scripts, no network: the page only needs its own style and an inline picture.
_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"


def _read(name: str) -> str:
    return resources.files("cornea.core.window").joinpath(name).read_text(encoding="utf-8")


def _icon_tag(path: Path | str | None) -> str:
    if path is None:
        return ""
    file = Path(path)
    try:
        data = base64.b64encode(file.read_bytes()).decode("ascii")
    except OSError:
        logger.warning("Could not read the loading screen icon %s", file, exc_info=True)
        return ""
    return f'<img alt="" src="data:{_IMAGE_TYPES[file.suffix.lower()]};base64,{data}">\n'


def _footer(footer: Html | str | None) -> str:
    if footer is None or not str(footer).strip():
        return ""
    body = str(footer) if isinstance(footer, Html) else html.escape(footer)
    return f"<footer>{body}</footer>\n"


def render_loading(loading: Loading, window: Window) -> str:
    """The page for the window: the custom one if given, else the built-in one."""
    if loading.html is not None:
        if isinstance(loading.html, Path):
            return loading.html.read_text(encoding="utf-8")
        return loading.html
    overrides = "".join(
        f"{name}: {value};"
        for name, value in (
            ("--custom-bg", str(loading.background) if loading.background else None),
            ("--custom-fg", str(loading.foreground) if loading.foreground else None),
        )
        if value is not None
    )
    scheme = {"auto": "light dark", "light": "light", "dark": "dark"}[loading.theme]
    title = html.escape(loading.title if loading.title is not None else window.title)
    return Template(_read("loading.html")).substitute(
        csp=_CSP,
        scheme=scheme,
        title=title,
        heading=title,
        subtitle=html.escape(loading.subtitle),
        icon=_icon_tag(loading.icon if loading.icon is not None else window.icon),
        footer=_footer(loading.footer),
        theme=loading.theme,
        overrides=overrides,
        css=_read("loading.css"),
    )


def check_loading(loading: Loading) -> None:
    """Fail before anything starts if the icon or the page file is not there."""
    if loading.icon is not None and not Path(loading.icon).is_file():
        raise FileNotFoundError(f"loading screen icon not found: {Path(loading.icon).resolve()}")
    if isinstance(loading.html, Path) and not loading.html.is_file():
        raise FileNotFoundError(f"loading screen page not found: {loading.html.resolve()}")


_THEME_BACKGROUND = {"light": Colour.LIGHT, "dark": Colour.DARK}


def splash_background(loading: Loading | None, window: Window) -> str | None:
    """The colour to paint the native window with while the loading screen loads.

    The window's own ``background`` wins. Otherwise it matches the built-in page: the loading
    ``background`` if that is hex, else the theme's colour (``auto`` follows the system's app
    mode). A replaced page (``Loading.html``) is unknown, so the window is left as it is.
    """
    if window.background is not None:
        return str(window.background)
    if loading is None or loading.html is not None:
        return None
    if loading.background is not None:
        try:
            return Colour(str(loading.background)).hex
        except ValueError:
            pass  # a colour name or rgb(): the theme's colour is the closest we can do
    theme = loading.theme
    if theme == "auto":
        theme = "dark" if system_prefers_dark() else "light"
    return _THEME_BACKGROUND[theme].hex
