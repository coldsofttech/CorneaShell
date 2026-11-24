"""Compare version numbers such as ``1.4.0``, ``v2.0`` and ``1.5.0rc1`` without extra packages."""

import re

_VERSION = re.compile(
    r"^v?(?P<release>\d+(?:\.\d+)*)(?:[-.]?(?P<kind>a|b|rc|alpha|beta|dev)\.?(?P<number>\d*))?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)
_ORDER = {"dev": 0, "a": 1, "alpha": 1, "b": 2, "beta": 2, "rc": 3}

Version = tuple[tuple[int, ...], int, int]


def parse_version(text: str) -> Version:
    """Turn a version into something that sorts. A pre-release sorts below its release.

    Raises:
        ValueError: If the text is not a version.

    Example:
        >>> parse_version("1.5.0rc1") < parse_version("1.5.0")
        True
        >>> parse_version("v1.10") > parse_version("1.9.9")
        True
    """
    match = _VERSION.match(text.strip())
    if match is None:
        raise ValueError(f"not a version number: {text!r}")
    release = [int(part) for part in match["release"].split(".")]
    while len(release) > 1 and release[-1] == 0:
        release.pop()  # 1.0 and 1.0.0 are the same version
    kind = match["kind"]
    if kind is None:
        return tuple(release), 4, 0
    return tuple(release), _ORDER[kind], int(match["number"] or 0)


def is_newer(candidate: str, current: str) -> bool:
    """Whether ``candidate`` is a later version than ``current``.

    Example:
        >>> is_newer("1.4.0", "1.3.9")
        True
        >>> is_newer("1.4.0", "1.4")
        False
    """
    return parse_version(candidate) > parse_version(current)
