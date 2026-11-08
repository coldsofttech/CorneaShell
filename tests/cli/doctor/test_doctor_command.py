import json
from pathlib import Path

import pytest

import cornea
from cli_support import runner
from cornea.cli import app, doctor


def test_doctor_shows_the_version(ready: None) -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert cornea.__version__ in result.output


def test_the_checks_start_with_the_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))  # doctor checks the log folder
    first = doctor.run_checks()[0]

    assert (first.name, first.status, first.detail) == ("Cornea", "ok", cornea.__version__)


def test_doctor_json(ready: None) -> None:
    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output)[0]["detail"] == cornea.__version__
