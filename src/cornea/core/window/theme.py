"""The system's light or dark choice for apps, which the loading screen follows."""

import logging
import sys

logger = logging.getLogger(__name__)

_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def system_prefers_dark() -> bool:
    """Whether Windows is set to dark mode for apps. Light when it cannot be read."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE) as key:
            return int(winreg.QueryValueEx(key, "AppsUseLightTheme")[0]) == 0
    except (OSError, ValueError):
        logger.debug("Could not read the app colour mode", exc_info=True)
        return False
