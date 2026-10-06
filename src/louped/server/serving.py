"""What `louped serve` does around the app: keep a checkout's UI build current, and record itself
per port so `--restart` stops that serve and no other process."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from louped import __version__
from louped.core import home

#: What apps/web's static export is built from, beside next.config.*.
UI_SOURCES = ("src", "public", "package.json", "pnpm-lock.yaml", "tsconfig.json",
              "postcss.config.mjs")  # fmt: skip
#: Seconds --restart waits for the old serve to exit and free its port.
WAIT = 30.0


def stale_ui(web: Path) -> Path | None:
    """The newest source under apps/web changed since its export (out/index.html) was built, or
    None when the export is current. A git checkout or pull sets the mtimes it writes to now."""
    built = (web / "out" / "index.html").stat().st_mtime
    newest, at = None, built
    for path in [*(web / n for n in UI_SOURCES), *web.glob("next.config.*")]:
        files = path.rglob("*") if path.is_dir() else [path] if path.is_file() else []
        for file in files:
            if file.is_file() and (mtime := file.stat().st_mtime) > at:
                newest, at = file, mtime
    return newest


def current_ui(web: Path) -> None:
    """Rebuild a checkout's UI with `pnpm build` when a source is newer than the build; without
    pnpm or apps/web/node_modules, say so and serve the old build."""
    changed = stale_ui(web)
    if changed is None:
        return
    why = f"{changed.relative_to(web)} is newer than the built UI in {web / 'out'}"
    if shutil.which("pnpm") is None or not (web / "node_modules").is_dir():
        print(f"warning: {why}, so the UI is out of date. Rebuild it: just web-build "
              f"(or cd {web} && pnpm build)")  # fmt: skip
        return
    print(f"{why}: rebuilding it with pnpm build in {web}")
    if subprocess.run(["pnpm", "build"], cwd=web).returncode != 0:
        raise SystemExit(f"pnpm build failed in {web}; fix the UI, or serve a build with --web-dir")


def record_path(port: int) -> Path:
    return home() / "serve" / f"{port}.json"


def recorded(port: int) -> dict | None:
    """The louped serve recorded for port: pid, host, port, started, louped, argv."""
    path = record_path(port)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def record(host: str, port: int) -> None:
    """Record this process as the louped serve on port."""
    path = record_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC).isoformat(timespec="seconds")
    found = {"pid": os.getpid(), "host": host, "port": port, "started": started,
             "louped": __version__, "argv": sys.argv}  # fmt: skip
    path.write_text(json.dumps(found, indent=2), encoding="utf-8")


def forget(port: int) -> None:
    """Remove port's record when it is this process's."""
    if (found := recorded(port)) is not None and found["pid"] == os.getpid():
        record_path(port).unlink(missing_ok=True)


def _cmdline(pid: int) -> list[str]:
    """The pid's command line; empty when it has exited (or is a zombie)."""
    proc = Path(f"/proc/{pid}/cmdline")
    if Path("/proc").is_dir():
        try:
            return [a for a in proc.read_bytes().decode(errors="replace").split("\0") if a]
        except OSError:
            return []
    ps = subprocess.run(["ps", "-o", "args=", "-p", str(pid)], capture_output=True, text=True)
    return ps.stdout.split()


def is_serve(pid: int, argv: list[str]) -> bool:
    """Whether pid is alive and is the louped serve that recorded argv: its command line ends with
    argv's arguments and runs louped. A reused pid is some other process."""
    args, line = argv[1:], _cmdline(pid)
    return ("serve" in args and len(line) > len(args) and line[len(line) - len(args):] == args
            and any("louped" in a for a in line[: len(line) - len(args)]))  # fmt: skip


def port_free(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # as uvicorn binds
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def claim(host: str, port: int, restart: bool) -> None:
    """Make way for a serve on port. With restart, stop the louped serve recorded for it (SIGTERM,
    then wait for it to exit); without, refuse when one runs. Says what it found."""
    found, path = recorded(port), record_path(port)
    alive = found is not None and is_serve(found["pid"], found["argv"])
    if found is not None and not alive:
        path.unlink(missing_ok=True)
    if not restart:
        if alive and found is not None:
            pid, started = found["pid"], found["started"]
            raise SystemExit(f"louped serve already runs on port {port} (pid {pid}, started "
                             f"{started}); pass --restart to replace it")  # fmt: skip
        return
    if found is None or not alive:
        gone = (f"pid {found['pid']} no longer runs louped serve" if found
                else f"none is recorded in {path.parent}")  # fmt: skip
        print(f"no louped serve to stop on port {port}: {gone}. Starting.")
        if not port_free(host, port):
            raise SystemExit(f"port {port} is taken by a process louped did not record; "
                             "it is not stopped. Free the port, or pass --port.")  # fmt: skip
        return
    pid = found["pid"]
    print(f"stopping louped serve pid {pid} on {found['host']}:{port} "
          f"(started {found['started']}, louped {found['louped']})")  # fmt: skip
    with contextlib.suppress(ProcessLookupError):  # it exited since
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + WAIT
    while is_serve(pid, found["argv"]) or not port_free(found["host"], port):
        if time.monotonic() > deadline:
            raise SystemExit(f"louped serve pid {pid} did not stop and free port {port} within "
                             f"{WAIT:.0f} s of SIGTERM; stop it with kill -9 {pid}")  # fmt: skip
        time.sleep(0.2)
    path.unlink(missing_ok=True)
