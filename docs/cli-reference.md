# `cornea`

Host a web UI in a native window with a secured local server.

**Usage**:

```console
$ cornea [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `-V, --version`: Show the version and exit.
* `-v, --verbose`: Show extra detail.
* `-q, --quiet`: Only show errors.
* `--no-color`: Disable colored output.
* `--help`: Show this message and exit.

**Commands**:

* `info`: Show version and environment details.

## `cornea info`

Show version and environment details.

**Usage**:

```console
$ cornea info [OPTIONS]
```

**Options**:

* `--json`: Output as JSON.
* `--help`: Show this message and exit.

## Examples

### `cornea`

```console
$ cornea --version
$ cornea --quiet info
$ cornea --no-color info
```

### `cornea info`

```console
$ cornea info
$ cornea info --json
```
