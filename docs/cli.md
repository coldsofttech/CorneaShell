# CLI reference

`cornea` is a command line tool built with [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/).

## Running

```bash
cornea --help          # installed script
python -m cornea.cli       # without relying on the script being on PATH
uvx --from cornea-shell cornea --help   # one-off, no install
```

## Global options

These go before the command name, for example `cornea --quiet info`.

| Option | Short | Description |
| --- | --- | --- |
| `--help` | | Show help for the tool or for a command. |
| `--version` | `-V` | Show the version and exit. |
| `--verbose` | `-v` | Show extra detail on stderr, and a traceback for unexpected errors. |
| `--quiet` | `-q` | Only show errors. Cannot be combined with `--verbose`. |
| `--no-color` | | Disable colored output. The standard `NO_COLOR` variable has the same effect. |
| `--install-completion` | | Install shell completion for the current shell. |
| `--show-completion` | | Print the completion script instead of installing it. |

The full, generated list of commands and options is in [cli-reference.md](cli-reference.md). Regenerate it after changing a command:

```bash
uv run typer cornea.cli utils docs --name cornea --output docs/cli-reference.md
```

CI fails if the file is out of date.

## Commands

### `info`

Show the tool version, the Python version and the platform in a table. Add `--json` for machine-readable output.

## Output conventions

- Results go to **stdout**, so they can be piped.
- Errors and extra detail go to **stderr**.
- `--json` prints a single JSON document to stdout, even with `--quiet`.
- Color is turned off automatically when output is piped, when `NO_COLOR` is set, or with `--no-color`.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | The command failed, for example an unexpected error. |
| `2` | Invalid usage, such as an unknown option or conflicting options. |

## Errors

Expected failures print `Error: <message>` to stderr and exit with code 1. Unexpected exceptions are caught by `run()` in `commands.py`: they print a one-line message and a hint to stderr, and show a traceback only with `--verbose`. Local variables are never shown, because they can contain secrets.

## Adding a command

1. Add the logic to `cornea.core` as a plain function that returns a value or raises an exception. It must not print or exit.
2. Add a command to `src/cornea/cli/commands.py` that calls it, writes through the consoles in `output.py`, and raises `typer.Exit(code=1)` on failure.
3. Add a `--json` option if the command returns data.
4. Add tests with `typer.testing.CliRunner`, document the command in this file, and regenerate `cli-reference.md`.
