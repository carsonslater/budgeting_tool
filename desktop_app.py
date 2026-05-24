#!/usr/bin/env python3
"""Launch the Household Budgeting app inside a Python desktop window."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

# --------------------------------------------------------------------
# Determine the directory where the .exe is located (PyInstaller-safe)
# --------------------------------------------------------------------
def resource_path(relative_path: str) -> str:
    """
    Return the absolute path to a resource, whether running as a script
    or as a PyInstaller bundle.
    """
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.argv[0])))
    return os.path.join(base_path, relative_path)


def find_free_port() -> int:
    """Return an available localhost port."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.getsockname()[1]


def wait_for_server(url: str, timeout: float = 30.0) -> None:
    """Block until the FastAPI app responds to /healthz or timeout is reached."""
    deadline = time.monotonic() + timeout
    health_url = f"{url}/healthz"

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1):
                return
        except (urllib.error.URLError, TimeoutError, ConnectionError, socket.timeout):
            time.sleep(0.25)

    raise TimeoutError(f"Timed out waiting for FastAPI app at {health_url}")


def launch_fastapi(port: int) -> subprocess.Popen:
    """Start the FastAPI uvicorn process and return the handle."""
    env = os.environ.copy()
    env.update({"PORT": str(port)})
    
    # Run uvicorn main:app from the backend folder so relative imports resolve
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", str(port)],
        env=env,
        cwd=resource_path("backend")
    )
    return process


def terminate_process(process: subprocess.Popen | None, *, timeout: float = 5.0) -> None:
    """Terminate the process gracefully, falling back to kill."""
    if process is None or process.poll() is not None:
        return

    process.terminate()

    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Run in dev mode, pointing webview to Vite server (localhost:5173).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for backend to start (default: %(default)s)",
    )

    args = parser.parse_args(argv)

    try:
        import webview  # type: ignore
    except ImportError as exc:  # pragma: no cover - import guard
        parser.error(
            "pywebview is required to launch the desktop window (install with 'pip install pywebview')."
        )
        raise exc

    process = None
    if args.dev:
        url = "http://localhost:5173"
        print(f"Running in dev mode. Ensure Vite is running at {url}")
    else:
        port = find_free_port()
        url = f"http://127.0.0.1:{port}"
        process = launch_fastapi(port)

        def handle_exit(signum, frame):  # type: ignore[override]
            terminate_process(process)
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)

        try:
            wait_for_server(url, timeout=args.timeout)
        except Exception:
            terminate_process(process)
            raise

    window = webview.create_window(
        "Household Budgeting", 
        url,
        width=1280,
        height=800,
        min_size=(1024, 768)
    )

    def on_closed() -> None:
        """Ensure the backend process stops if the window is closed."""
        terminate_process(process)

    window.events.closed += on_closed  # type: ignore[attr-defined]

    try:
        webview.start()
    finally:
        terminate_process(process)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
