"""The settings file of the cornea command: where it is found, what it may say, who wins."""

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cornea import Process, Static, Url, Window
from cornea.cli import app, config

runner = CliRunner()


class Calls:
    """Stands in for run(): remembers how the command called it."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def __call__(self, source: Any = None, **kwargs: Any) -> None:
        self.items.append({"source": source, **kwargs})

    @property
    def last(self) -> dict[str, Any]:
        return self.items[-1]


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Calls:
    recorded = Calls()
    monkeypatch.setattr("cornea.cli.commands.run_shell", recorded)
    monkeypatch.chdir(tmp_path)
    return recorded


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ----- finding the file -------------------------------------------------------------------------


def test_cornea_toml_is_found_in_the_folder(tmp_path: Path) -> None:
    file = write(tmp_path / "cornea.toml", "[window]\ntitle = 'x'\n")

    assert config.find_config(tmp_path) == file


def test_it_is_found_in_a_parent_folder(tmp_path: Path) -> None:
    file = write(tmp_path / "cornea.toml", "[window]\ntitle = 'x'\n")
    inner = tmp_path / "a" / "b"
    inner.mkdir(parents=True)

    assert config.find_config(inner) == file


def test_the_tool_table_of_pyproject_counts(tmp_path: Path) -> None:
    file = write(tmp_path / "pyproject.toml", "[tool.cornea.window]\ntitle = 'x'\n")

    assert config.find_config(tmp_path) == file


def test_a_pyproject_without_the_table_is_skipped(tmp_path: Path) -> None:
    write(tmp_path / "pyproject.toml", "[project]\nname = 'x'\n")
    outer = write(tmp_path / "cornea.toml", "[window]\ntitle = 'x'\n")
    inner = tmp_path / "pkg"
    write(inner / "pyproject.toml", "[project]\nname = 'y'\n")

    assert config.find_config(inner) == outer


def test_the_nearest_file_wins_and_files_are_not_merged(tmp_path: Path) -> None:
    write(tmp_path / "cornea.toml", "[window]\ntitle = 'outer'\n[server]\nport = 1\n")
    inner = write(tmp_path / "pkg" / "cornea.toml", "[window]\ntitle = 'inner'\n")

    found = config.find_config(inner.parent)
    assert found == inner
    assert "port" not in config.load_config(inner)["open"]


def test_cornea_toml_beats_pyproject_in_the_same_folder(tmp_path: Path) -> None:
    file = write(tmp_path / "cornea.toml", "[window]\ntitle = 'x'\n")
    write(tmp_path / "pyproject.toml", "[tool.cornea.window]\ntitle = 'y'\n")

    assert config.find_config(tmp_path) == file


# ----- reading it -------------------------------------------------------------------------------


def test_keys_may_use_dashes_or_underscores(tmp_path: Path) -> None:
    file = write(tmp_path / "cornea.toml", "[window]\non-top = true\nmin_size = '10x10'\n")

    values = config.load_config(file)["open"]

    assert values["on_top"] is True
    assert values["min_size"] == "10x10"


def test_a_single_value_may_stand_for_a_list(tmp_path: Path) -> None:
    file = write(tmp_path / "cornea.toml", "[security]\nallowed-host = 'a.test'\n")

    assert config.load_config(file)["open"]["allowed_host"] == ["a.test"]


def test_paths_are_relative_to_the_file(tmp_path: Path) -> None:
    file = write(tmp_path / "cornea.toml", "[window]\nicon = 'assets/icon.png'\n")

    assert config.load_config(file)["open"]["icon"] == str(tmp_path / "assets" / "icon.png")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[nothing]\nx = 1\n", "unknown table"),
        ("[window]\ncolour = 'red'\n", "unknown key 'colour'"),
        ("[window\n", "not valid TOML"),
    ],
)
def test_a_bad_file_is_an_error(tmp_path: Path, text: str, message: str) -> None:
    file = write(tmp_path / "cornea.toml", text)

    with pytest.raises(config.ConfigError, match=message):
        config.load_config(file)


# ----- the command ------------------------------------------------------------------------------


def test_the_file_sets_defaults(calls: Calls, tmp_path: Path) -> None:
    write(tmp_path / "cornea.toml", "[source]\nweb-dist = 'site'\n[window]\ntitle = 'From file'\n")

    result = runner.invoke(app, ["open"])

    assert result.exit_code == 0
    assert calls.last["source"] == Static(path=tmp_path / "site")
    assert calls.last["window"] == Window(title="From file")
    assert "cornea.toml" in result.stderr


def test_a_flag_beats_the_file(calls: Calls, tmp_path: Path) -> None:
    write(tmp_path / "cornea.toml", "[window]\ntitle = 'From file'\n")

    runner.invoke(app, ["open", "web", "--title", "From flag"])

    assert calls.last["window"].title == "From flag"


def test_a_source_on_the_command_line_replaces_the_files_source(
    calls: Calls, tmp_path: Path
) -> None:
    write(
        tmp_path / "cornea.toml",
        "[source]\nrun = 'npm run dev'\nurl = 'http://localhost:5173'\nmode = 'proxy'\n",
    )

    result = runner.invoke(app, ["open", "web"])

    assert result.exit_code == 0
    assert isinstance(calls.last["source"], Static)


def test_the_file_can_start_a_dev_server(calls: Calls, tmp_path: Path) -> None:
    write(
        tmp_path / "cornea.toml",
        "[source]\nrun = 'npm run dev'\nurl = 'http://localhost:5173'\nmode = 'proxy'\n"
        "[window]\nframeless = true\n",
    )

    result = runner.invoke(app, ["open"])

    assert result.exit_code == 0
    assert calls.last["source"] == Process("npm run dev", url="http://localhost:5173", mode="proxy")
    assert calls.last["window"].frameless is True


def test_serve_reads_the_shared_tables(calls: Calls, tmp_path: Path) -> None:
    write(tmp_path / "cornea.toml", "[source]\nurl = 'http://localhost:5173'\nmode = 'proxy'\n")

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 0
    assert calls.last["source"] == Url("http://localhost:5173", mode="proxy")


def test_no_config_ignores_the_file(calls: Calls, tmp_path: Path) -> None:
    write(tmp_path / "cornea.toml", "[window]\ntitle = 'From file'\n")

    runner.invoke(app, ["--no-config", "open", "web"])

    assert calls.last["window"].title != "From file"


def test_config_names_a_file(calls: Calls, tmp_path: Path) -> None:
    other = write(tmp_path / "elsewhere" / "mine.toml", "[window]\ntitle = 'Mine'\n")

    runner.invoke(app, ["--config", str(other), "open", "web"])

    assert calls.last["window"].title == "Mine"


def test_config_and_no_config_conflict(calls: Calls, tmp_path: Path) -> None:
    result = runner.invoke(app, ["--config", "x.toml", "--no-config", "open", "web"])

    assert result.exit_code == 2


def test_a_missing_config_file_is_a_short_error(calls: Calls) -> None:
    result = runner.invoke(app, ["--config", "missing.toml", "open", "web"])

    assert result.exit_code == 2
    assert "cannot read" in result.stderr
    assert not calls.items


def test_a_bad_file_stops_the_command(calls: Calls, tmp_path: Path) -> None:
    write(tmp_path / "cornea.toml", "[window]\ncolour = 'red'\n")

    result = runner.invoke(app, ["open", "web"])

    assert result.exit_code == 2
    assert "unknown key" in result.stderr
    assert not calls.items


def test_doctor_reports_a_bad_file(
    calls: Calls, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    write(tmp_path / "cornea.toml", "[window]\ncolour = 'red'\n")

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1  # a problem, not a crash: the other commands refuse with 2
    assert "unknown key" in result.stdout
