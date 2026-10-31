# CorneaShell

[![CI](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cornea-shell)](https://pypi.org/project/cornea-shell/)
[![Python versions](https://img.shields.io/pypi/pyversions/cornea-shell)](https://pypi.org/project/cornea-shell/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/github/license/coldsofttech/CorneaShell)](LICENSE)

A ready-to-use starting point for public Python projects on GitHub. It includes a typed package layout, automated testing on Python 3.11 to 3.15, linting, one-step releases to PyPI, and the community and security files a public repository needs.

## What you get

- A typed `src` package with tests and a coverage minimum
- Fast, reproducible setup with [uv](https://docs.astral.sh/uv/)
- Linting, formatting and type checking before every commit and in CI
- Automated tests on Python 3.11 to 3.15 (Ubuntu) and 3.11 (Windows and macOS)
- Publishing to PyPI when you create a GitHub release, with no stored tokens
- Contribution, conduct, support and security-reporting guidelines
- Issue forms, a pull request template and automated dependency updates

## Getting started

1. Click **Use this template** on GitHub and create your new repository.
2. Run the **Init** workflow from the Actions tab and merge the pull request it opens. This fills in your owner and repository name.
3. Rename the example package and set your project description. See the [development guide](docs/development.md).
4. Add your contact details in `CODE_OF_CONDUCT.md`, delete `.github/workflows/init.yml`, and replace this description.
5. Apply the repository protections by following the [setup guide](docs/repo-setup.md).
6. Install dependencies and commit checks:

   ```bash
   uv sync
   uv run pre-commit install --hook-type pre-commit --hook-type post-commit
   ```

## Installation

Requires Python 3.11 or newer.

```bash
pip install cornea-shell
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add cornea-shell
```

To install the latest development version from source:

```bash
pip install git+https://github.com/coldsofttech/CorneaShell.git
```

## Usage

```python
import cornea

print(cornea.__version__)
```


## Development

```bash
git clone https://github.com/coldsofttech/CorneaShell.git
cd CorneaShell
uv sync
uv run pytest
```

See the [development guide](docs/development.md) for linting, type checking and releasing.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Please report security issues privately as described in [SECURITY.md](SECURITY.md).

## License

Released under the [MIT License](LICENSE).
