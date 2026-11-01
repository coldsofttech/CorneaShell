# PHP

**Not run on the author's machine (PHP is not installed there). Tested by the examples workflow.**

A tiny PHP server that Cornea starts and shows. It has a page at `/` and a JSON answer at `/hello?name=Zed`.

```bash
uv run cornea open --run "php -S 127.0.0.1:5103 -t examples/php_server examples/php_server/index.php" --url http://127.0.0.1:5103 --mode proxy
uv run python examples/php_server/main.py                        # Python, through the proxy
uv run python examples/php_server/main.py --mode direct          # Python, a window without the proxy
```

Needs PHP 8. The last argument of `php -S` is the router that sends every request to `index.php`.
