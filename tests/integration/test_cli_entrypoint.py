import subprocess
import sys
from pathlib import Path

import cornea


def _run(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def test_module_entrypoint() -> None:
    result = _run(sys.executable, "-m", "cornea.cli", "--version")

    assert result.returncode == 0
    assert cornea.__version__ in result.stdout


def test_console_script() -> None:
    script = Path(sys.executable).parent / ("cornea.exe" if sys.platform == "win32" else "cornea")

    result = _run(str(script), "--version")

    assert result.returncode == 0
    assert cornea.__version__ in result.stdout


def test_errors_go_to_stderr() -> None:
    result = _run(sys.executable, "-m", "cornea.cli", "--verbose", "--quiet", "info")

    assert result.returncode == 2
    assert result.stdout == ""
