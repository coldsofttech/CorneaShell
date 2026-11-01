#!/usr/bin/env python3
"""Measure how long Cornea takes to start, on this machine.

Usage: uv run python scripts/measure_startup.py [runs]   (default 5)

Every run is a separate process, so nothing is warm. Two cases are measured:

* headless: ``Shell(window=None)``, up to the point where the server accepts requests
* window:   a real window on a tiny bundle, up to the point where its first page has loaded

Times are seconds since ``Shell.run()`` (or ``start()``) began; ``import`` is the time to import
``cornea`` before that. The documented target lives in docs/architecture.md.
"""

import json
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

CASES = {
    "headless": ("import", "server_ready"),
    "window": ("import", "server_ready", "window_shown", "page_loaded"),
}


def child(case: str) -> None:
    """Run one start-up and print its timings as one JSON line."""
    began = time.perf_counter()
    from cornea import Shell, Static, Window

    result: dict[str, float | None] = {"import": time.perf_counter() - began}
    bundle = Path(tempfile.mkdtemp())
    (bundle / "index.html").write_text("<html><body>hello</body></html>", encoding="utf-8")
    if case == "headless":
        shell = Shell(Static(bundle), window=None)
        with shell:
            result["server_ready"] = shell.timings.server_ready
    else:
        shell = Shell(Static(bundle), window=Window(size=(600, 400)))

        def close_when_loaded() -> None:
            import webview

            deadline = time.time() + 60
            while time.time() < deadline and shell.timings.page_loaded is None:
                time.sleep(0.02)
            webview.windows[0].destroy()

        threading.Thread(target=close_when_loaded, daemon=True).start()
        shell.run()
        timings = shell.timings
        result.update(
            server_ready=timings.server_ready,
            window_shown=timings.window_shown,
            page_loaded=timings.page_loaded,
        )
    sys.stdout.write("TIMINGS " + json.dumps(result) + "\n")


def run_case(case: str, runs: int) -> dict[str, list[float]]:
    samples: dict[str, list[float]] = {name: [] for name in CASES[case]}
    for _ in range(runs):
        done = subprocess.run(
            [sys.executable, __file__, "--child", case],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        lines = [line for line in done.stdout.splitlines() if line.startswith("TIMINGS ")]
        if not lines:
            sys.exit(f"{case}: no timings.\n{done.stdout}\n{done.stderr}")
        for name, value in json.loads(lines[-1].removeprefix("TIMINGS ")).items():
            if value is not None:
                samples[name].append(value)
    return samples


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        child(sys.argv[2])
        return
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(f"Cornea start-up, {runs} runs each, in seconds since run() began")
    for case in CASES:
        samples = run_case(case, runs)
        print(f"\n{case}")
        print(f"  {'step':<14}{'median':>8}{'min':>8}{'max':>8}")
        for name, values in samples.items():
            if values:
                print(
                    f"  {name:<14}{statistics.median(values):>8.2f}"
                    f"{min(values):>8.2f}{max(values):>8.2f}"
                )


if __name__ == "__main__":
    main()
