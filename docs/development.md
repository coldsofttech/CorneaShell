# Development

## Layout

```text
src/cornea/            package source (src layout, typed)
src/cornea/core/       server, security, sources, window and bridge
src/cornea/cli/        command line interface (thin wrapper over the Python API)
tests/                 pytest tests
pyproject.toml         metadata, dependencies and tool configuration
uv.lock                locked dependencies (commit this file)
```

The distribution is named `cornea-shell`, the import is `cornea`, and the command is `cornea`.

## Tooling

| Purpose | Tool |
| --- | --- |
| Environment, dependencies, build | [uv](https://docs.astral.sh/uv/) with Hatchling |
| Lint and format | Ruff |
| Type checking | mypy (strict) |
| Tests and coverage | pytest with pytest-cov (80% minimum) |

```bash
uv sync                    # create .venv and install dev dependencies
uv run pytest              # unit tests with coverage (skips integration tests)
uv run pytest -m integration --no-cov   # integration tests only
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy                # type check
uv build                   # build sdist and wheel
```

## Integration tests

Tests under `tests/integration/` are marked `integration` automatically by that folder's `conftest.py`. They are excluded from the default `pytest` run, and therefore from the pre-commit hook, and run as their own job in CI. Put slower or end-to-end tests there.

## Start-up time

`cornea open <folder> --measure` (or `Shell(measure=True)`) shows how long start-up took. Add `--json-file timings.json` to keep the numbers, and run it a few times to compare. The window case needs WebView2. See [startup time](architecture.md#startup-time) for the target.

## The stand-in dev server

`tests/devserver.py` is a tiny dev server that the `Process` tests start as their command, so they need neither Node nor a real framework. The crash test under `tests/integration/` uses it to prove that the server is gone after Cornea dies.

## Continuous integration

The `ci` workflow runs four jobs. `lint` runs on Linux: pre-commit (Ruff and mypy among others) and the checks that the generated references are up to date. It also shows that the package imports without pywebview. `test` (unit tests with coverage), `integration` (tests marked `integration`, which run real processes and a real window) and `build` (build, `twine check`, and a smoke test of the built wheel in a clean environment) run on Windows, because that is where Cornea shows a window. `test` and `integration` run on Python 3.11 to 3.15, and install without the `hooks` dependency group (pre-commit and its PyYAML), which they do not use and which can lack a Windows build for the newest Python. A plain `uv sync` installs it. A final `ci` job gates on all four and is the single required check in the branch ruleset.

The real-window test skips itself when the runner has no WebView2 runtime; `-rs` lists skipped tests in the log. The weekly `audit` workflow also runs on Windows, so it checks the Windows-only dependencies (pywebview and pythonnet) too.

## Examples

The projects in `examples/` are run by the unit tests, except the React one, which needs `npm install && npm run build` first. Flask and Django are development dependencies only, for those tests.

## Releasing to PyPI

Publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no API token is stored.

1. On PyPI, add a trusted publisher for this repository: workflow `release.yml`, environment `pypi`.
2. Create an environment named `pypi` in the repository settings and restrict its deployment branches and tags to `v*` tags.
3. Bump `__version__` in `src/<package>/__init__.py` and update `CHANGELOG.md`.
4. Publish a GitHub release tagged `v<version>`. The workflow fails if the tag and version differ.
