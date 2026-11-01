# Go

**Not run on the author's machine (Go is not installed there). Tested by the examples workflow.**

A tiny Go server that Cornea starts and shows. It has a page at `/` and a JSON answer at `/hello?name=Zed`.

```bash
uv run cornea open --run "go run . 5104" --run-cwd examples/go_server --url http://127.0.0.1:5104 --mode proxy --run-timeout 120
uv run python examples/go_server/main.py                        # Python, through the proxy
uv run python examples/go_server/main.py --mode direct          # Python, a window without the proxy
```

Needs Go 1.21 or newer.
