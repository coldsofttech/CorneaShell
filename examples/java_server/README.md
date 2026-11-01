# Java

**Not run on the author's machine (Java is not installed there). Tested by the examples workflow.**

A tiny Java server that Cornea starts and shows. It has a page at `/` and a JSON answer at `/hello?name=Zed`.

```bash
uv run cornea open --run "java Server.java 5102" --run-cwd examples/java_server --url http://127.0.0.1:5102 --mode proxy
uv run python examples/java_server/main.py                        # Python, through the proxy
uv run python examples/java_server/main.py --mode direct          # Python, a window without the proxy
```

Needs JDK 21 or newer. `java Server.java` runs the source file directly.
