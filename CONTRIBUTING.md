# Contributing to Cornea Shell

Thanks for helping. Cornea Shell sits between a web page and the person's computer, so changes are reviewed with extra care for security.

## Getting started

```bash
uv sync
uv run pre-commit install --hook-type pre-commit --hook-type post-commit
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

Development uses **Python 3.11**, the minimum supported version (see `.python-version`). Please do not use syntax or standard library features newer than 3.11. CI runs 3.11 to 3.15 on Windows, because Cornea shows a Windows window.

More detail is in [docs/development.md](docs/development.md) and [docs/architecture.md](docs/architecture.md).

## Where things live

- `src/cornea/core/` is the library, in subpackages: `app/`, `window/`, `bridge/`, `sources/`, `security/` and `page/`.
- `src/cornea/cli/` is the `cornea` command, a thin wrapper over the Python API.
- `tests/core/` and `tests/cli/` mirror those folders. Slower tests go in an `integration/` folder next to them and run with `pytest -m integration`. Tests that run the example projects go in `examples/`.
- `examples/` has one folder per example, each with its own README.
- `docs/api-reference.md` and `docs/cli-reference.md` are written by hand, except for the blocks between `GENERATED` markers (the API from the code and docstrings, the usage, options and examples from the CLI). After changing the public API or the command line, run `uv run python scripts/gen_api_reference.py` and `uv run python scripts/gen_cli_reference.py`. CI fails if they are out of date.

## Ground rules

1. **Security first.** The page is untrusted. Native actions that touch files, the network or other programs stay off until the app turns them on, and anything the page sends is checked. A change that weakens a protection needs a strong justification and tests. See the [Security Policy](SECURITY.md).
2. **Tests come with every change.** Bug fixes need a regression test. Coverage stays at or above the minimum in `pyproject.toml`.
3. **Keep dependencies minimal.** Optional features go in extras, not in the main dependencies.
4. **Type everything.** mypy runs in strict mode and Ruff handles lint and formatting (line length 100).
5. **Write for users.** The README and the changelog describe what changed from a user's point of view; technical detail goes in `docs/`.

## Pull requests

- Branch from `main`; keep the change focused.
- Make sure tests, Ruff and mypy pass locally.
- Add a short entry under `[Unreleased]` in `CHANGELOG.md` (one or two lines, no file or function names).
- Describe the behaviour change and any security impact.
- Fill in the pull request template.
- `main` is protected: changes land through pull requests that are squash-merged, after the required checks pass, a code owner has reviewed and every conversation is resolved.

Use [Conventional Commits](https://www.conventionalcommits.org/) for the title, for example `fix: handle empty input`.

By contributing you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md) and that your contribution is licensed under the project's MIT license.
