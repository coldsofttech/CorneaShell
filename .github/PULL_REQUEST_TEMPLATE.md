## What does this change?

<!-- A short description and the motivation. Link the issue if there is one, e.g. Closes #123. -->

## Security check

- [ ] The page is still treated as untrusted: nothing new is reachable without the session cookie
- [ ] New native actions are off by default and validate what the page sends
- [ ] No secrets, tokens or personal data are logged or committed

## Checklist

- [ ] The change is focused on one thing
- [ ] Tests added or updated in `tests/core/` or `tests/cli/` (slower ones under `integration/`)
- [ ] `uv run pytest`, `ruff check .`, `ruff format --check .` and `mypy` pass
- [ ] `CHANGELOG.md` has a short `[Unreleased]` entry
- [ ] `README.md` or `docs/` are updated if behavior changed (regenerate `docs/api-reference.md` and `docs/cli-reference.md` with `scripts/`)
- [ ] Works on Python 3.11
