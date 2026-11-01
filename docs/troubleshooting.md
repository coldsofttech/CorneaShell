# Troubleshooting

Start with two commands. `cornea info` shows the versions Cornea runs on, including the WebView2 runtime and the log folder. Running with `--debug` (or `--log-level debug --log-file cornea.log`) writes a log you can read or attach to a bug report. The log never contains the start-up token, cookies, or what your page sends to an action.

## The window does not open

| Message or sign | What it means | What to do |
| --- | --- | --- |
| `Cornea windows only work on Windows for now.` | Windows are only supported on Windows. | Use `cornea serve` and open the address in a browser on any system. |
| `The Microsoft Edge WebView2 runtime is not installed.` | The window engine is missing. | Install it from the link in the message, then run again. |
| `pywebview is not installed.` | The window library did not install. | `pip install --force-reinstall cornea-shell`. |
| `a direct URL cannot use a frameless window` | A page Cornea does not serve cannot reach the window controls. | Add `--mode proxy`, or `--js-api` for a page you trust, or drop `--frameless`. |
| `window icon not found: ...` | The `--icon` file does not exist. | Check the path. |

## The page is blank or shows an error

| Sign | What it means | What to do |
| --- | --- | --- |
| `The start-up link is not valid` | The one-time start-up link was already used or has expired. | Start Cornea again and open the new address. Reloading the first link does not work. |
| `Unexpected Host` or `Unexpected Origin` (403) | The page was reached through an address Cornea does not allow. | Add the host with `--allowed-host`. The log shows a warning with the path. |
| `Not signed in` (401) | The request has no session cookie. | Open the page through the start-up address, not by typing the port. |
| Scripts or styles do nothing, and the developer tools show a Content-Security-Policy error | The default policy blocks inline scripts and styles. | Move them into files. For a development server only, add `--csp-profile dev`. Never use it for something you ship. |
| A 502 page that names an address | The server behind `--mode proxy` is not answering. | Start it, or check the address. The log says why. |

## A dev server started with `--run`

| Message | What to do |
| --- | --- |
| `... exited with code N before ... was ready.` | The message ends with the command's last output; fix what it says. |
| `... did not answer within N seconds` | Check the `--url` matches the port the server really uses, or raise `--run-timeout`. |
| `Something is already listening on ...` | Stop the other server, or use `--url` alone to show it. |
| `could not start ...` | The program is not installed or not on the path. |

## Notifications, dropped files and opened files

| Sign | What to do |
| --- | --- |
| `Notifications need the extra: pip install "cornea-shell[notifications]"` | Install the extra. |
| The page gets `available: false` from `show_notification` | There is no window (`serve`), the extra is missing, or this is not Windows. |
| `Unknown action` for `show_notification`, `open_file` or `reveal` | They are off until you add `--notifications` or `--open-files`. |
| `cornea:drop` never arrives | Start with `--drop-files`, and drop on the page, not on the title bar. |
| `files of that type cannot be opened from a page` | `open_file` never opens programs, scripts or shortcuts. Use `reveal` to show them. |
| The window will not close | An app close guard or the page is holding it. Look for `cornea:close-blocked` in the page; `POST /api/window/close` with `{"force": true}` closes anyway. |

## Settings and files

| Message | What to do |
| --- | --- |
| `unknown key ... in [table]` or `unknown table [...]` | A typo in `cornea.toml`; the message lists the accepted names. |
| `cannot read ...` or `... is not valid TOML` | Check the path given to `--config`, or the file's syntax. |
| `single_instance and remember_window need a window` | These options need a window, so they work with `open`, not `serve`. |
| `could not open the log file` | The `--log-file` folder cannot be written. Debug mode's own log falls back to the screen. |

## Still stuck

Run with `--debug`, reproduce the problem, and open an issue with the output of `cornea info` and the log file. Please report anything that looks like a security problem privately, as described in `SECURITY.md`.
