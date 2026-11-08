"""The loading screen: a small page the window shows before the app is ready."""

import base64
import html
import logging
from importlib import resources
from pathlib import Path
from string import Template

from cornea.core.config import Loading, Window

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


def render_loading(loading: Loading, window: Window) -> str:
    """The page for the window: the custom one if given, else the built-in one."""
    if loading.html is not None:
        if isinstance(loading.html, Path):
            return loading.html.read_text(encoding="utf-8")
        return loading.html
    overrides = "".join(
        f"{name}: {value};"
        for name, value in (
            ("--custom-bg", loading.background),
            ("--custom-fg", loading.foreground),
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
