"""louped serve around the app: a checkout's UI build kept current, and --restart stopping the
serve it recorded and nothing else."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from louped.server import serving


def test_a_ui_build_is_stale_when_any_of_its_sources_is_newer(tmp_path: Path) -> None:
    web = tmp_path / "web"
    (web / "src" / "app").mkdir(parents=True)
    (web / "out").mkdir()
    for name in ("package.json", "src/app/page.tsx", "next.config.ts", "README.md"):
        (web / name).write_text("x")
        os.utime(web / name, (100, 100))
    (web / "out" / "index.html").write_text("<p>built</p>")
    os.utime(web / "out" / "index.html", (200, 200))
    assert serving.stale_ui(web) is None
    os.utime(web / "README.md", (300, 300))  # not a source of the build
    assert serving.stale_ui(web) is None
    os.utime(web / "next.config.ts", (300, 300))
    os.utime(web / "src" / "app" / "page.tsx", (400, 400))
    assert serving.stale_ui(web) == web / "src" / "app" / "page.tsx"  # the newest


def test_a_stale_ui_without_pnpm_says_how_to_rebuild_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    web = tmp_path / "web"
    (web / "out").mkdir(parents=True)
    (web / "out" / "index.html").write_text("<p>built</p>")
    os.utime(web / "out" / "index.html", (100, 100))
    (web / "package.json").write_text("{}")
    monkeypatch.setattr(serving.shutil, "which", lambda name: None)
    serving.current_ui(web)
    out = capsys.readouterr().out
    assert "package.json is newer than the built UI" in out and "pnpm build" in out


def fake_serve(port: int, ignore_term: bool = False) -> subprocess.Popen[bytes]:
    """A process whose command line is a louped serve's, as /proc shows it."""
    code = "import signal, time\n"
    if ignore_term:
        code += "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    code += "print('up', flush=True)\ntime.sleep(60)\n"
    argv = [sys.executable, "-c", code, "louped", "serve", "--port", str(port)]
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE)
    assert proc.stdout is not None and proc.stdout.readline() == b"up\n"
    return proc


def write_record(pid: int, port: int) -> None:
    path = serving.record_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    found = {"pid": pid, "host": "127.0.0.1", "port": port, "started": "now", "louped": "0",
             "argv": ["/bin/louped", "serve", "--port", str(port)]}  # fmt: skip
    path.write_text(json.dumps(found))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(not Path("/proc").is_dir(), reason="reads /proc")
def test_restart_stops_the_recorded_serve_and_only_it(capsys: pytest.CaptureFixture[str]) -> None:
    port = free_port()
    serving.record("127.0.0.1", port)  # this process records itself, and forgets on exit
    assert serving.recorded(port)["pid"] == os.getpid()  # type: ignore[index]
    serving.forget(port)
    assert serving.recorded(port) is None

    proc = fake_serve(port)
    write_record(proc.pid, port)
    assert serving.is_serve(proc.pid, serving.recorded(port)["argv"])  # type: ignore[index]
    assert not serving.is_serve(os.getpid(), serving.recorded(port)["argv"])  # type: ignore[index]
    with pytest.raises(SystemExit, match="already runs on port"):
        serving.claim("127.0.0.1", port, restart=False)
    serving.claim("127.0.0.1", port, restart=True)
    assert proc.wait(5) != 0 and serving.recorded(port) is None
    assert f"stopping louped serve pid {proc.pid}" in capsys.readouterr().out

    # a recorded pid that is now another process is not stopped
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    write_record(other.pid, port)
    serving.claim("127.0.0.1", port, restart=True)
    assert other.poll() is None and "no longer runs louped serve" in capsys.readouterr().out
    other.kill()
    other.wait()
    serving.claim("127.0.0.1", port, restart=True)
    assert "none is recorded" in capsys.readouterr().out

    # a port held by something louped did not record is left alone
    with socket.socket() as held:
        held.bind(("127.0.0.1", port))
        held.listen()
        with pytest.raises(SystemExit, match="louped did not record"):
            serving.claim("127.0.0.1", port, restart=True)


@pytest.mark.skipif(not Path("/proc").is_dir(), reason="reads /proc")
def test_restart_says_so_when_the_old_serve_will_not_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    port = free_port()
    proc = fake_serve(port, ignore_term=True)
    write_record(proc.pid, port)
    monkeypatch.setattr(serving, "WAIT", 0.5)
    try:
        with pytest.raises(SystemExit, match=f"kill -9 {proc.pid}"):
            serving.claim("127.0.0.1", port, restart=True)
    finally:
        proc.kill()
        proc.wait()
