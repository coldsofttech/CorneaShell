# ASP.NET Core

**Not run on the author's machine (.NET SDK is not installed there). Tested by the examples workflow.**

A tiny ASP.NET Core server that Cornea starts and shows. It has a page at `/` and a JSON answer at `/hello?name=Zed`.

```bash
uv run cornea open --run "dotnet run --project examples/dotnet_server --urls http://127.0.0.1:5101" --url http://127.0.0.1:5101 --mode proxy --run-timeout 120
uv run python examples/dotnet_server/main.py                        # Python, through the proxy
uv run python examples/dotnet_server/main.py --mode direct          # Python, a window without the proxy
```

Needs the .NET 8 SDK. The first start restores and compiles, so it takes a while.
