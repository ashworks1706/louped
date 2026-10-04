"""Attribution graphs with circuit-tracer, into <home>/graphs, where the app's Circuits page shows
them in circuit-tracer's own viewer.

    louped circuit --model Qwen/Qwen3-0.6B --transcoders mwhanna/qwen3-0.6b-transcoders-lowl0 \\
        --prompt "The capital of the state containing Dallas is"

circuit-tracer pins its own transformers, so it runs in an environment of its own that uv builds
and caches on first use (`uvx`); louped only needs uv on the PATH. Each graph gets a RunMeta file
beside it, and the viewer is copied from the same circuit-tracer version, so graph and viewer
always match.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from louped.core import capture, graphs_dir

VERSION = "0.5.0"


def _uvx() -> list[str]:
    uvx = shutil.which("uvx")
    if uvx is None:
        raise RuntimeError(
            "louped circuit runs circuit-tracer through uv: install uv (pip install uv)"
        )
    # a uv-managed Python ships its headers, which Triton compiles its CUDA helpers against
    return [uvx, "--managed-python", "--from", f"circuit-tracer=={VERSION}"]


def _env(cpu: bool = False) -> dict[str, str]:
    """The environment circuit-tracer runs in: uv may fetch its managed Python even when the user's
    uv config says downloads are manual; with cpu, no GPU at all."""
    env = os.environ | {"UV_PYTHON_DOWNLOADS": "automatic"}
    return env | {"CUDA_VISIBLE_DEVICES": ""} if cpu else env


def _attribute(cmd: list[str], env: dict[str, str]) -> tuple[int, str]:
    """Run circuit-tracer, echoing its output; its exit code and the end of its output."""
    tail: list[str] = []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          env=env) as proc:  # fmt: skip
        for line in proc.stdout or []:
            print(line, end="", flush=True)
            tail = [*tail[-200:], line]
    return proc.returncode, "".join(tail)


def circuit(
    model: str,
    transcoders: str,
    prompt: str,
    slug: str = "graph",
    dtype: str = "bfloat16",
    batch_size: int = 64,
    extra: list[str] | None = None,
) -> Path:
    """One attribution graph of the prompt, its metadata and the viewer; returns the graphs dir.

    It adapts to the GPU: out of memory, the backward batch halves down to 8, then the model's
    weights move to the CPU and the transcoders' encoders load lazily, and last it runs on the CPU
    alone. Each step is slower and each fits a smaller GPU.
    """
    graphs = graphs_dir()
    graphs.mkdir(parents=True, exist_ok=True)
    tool = _uvx()
    base = [*tool, "circuit-tracer", "attribute", "-m", model, "-t", transcoders, "-p", prompt,
            "--slug", slug, "--graph_file_dir", str(graphs), "--dtype", dtype,
            *(extra or [])]  # fmt: skip
    sizes = [batch_size]
    while sizes[-1] > 8:
        sizes.append(sizes[-1] // 2)
    lazy = ["--offload", "cpu", "--lazy-encoder"]
    steps = [*((b, [], False) for b in sizes), (8, lazy, False), (8, ["--lazy-encoder"], True)]
    for n, (size, flags, cpu) in enumerate(steps):
        cmd = [*base, "--batch_size", str(size), *flags]
        code, out = _attribute(cmd, _env(cpu))
        if code == 0:
            break
        if "OutOfMemoryError" not in out or n == len(steps) - 1:
            raise subprocess.CalledProcessError(code, cmd, out)
        after = steps[n + 1]
        where = "on the CPU" if after[2] else "offloaded" if after[1] else f"batch {after[0]}"
        print(f"out of GPU memory: again, {where}", flush=True)
    (graphs / f"{slug}.meta.json").write_text(capture().model_dump_json(indent=2))
    find = "import circuit_tracer.frontend as f, pathlib; print(pathlib.Path(f.__file__).parent)"
    done = subprocess.run([*tool, "python", "-c", find], check=True, capture_output=True,
                          text=True, env=_env())  # fmt: skip
    assets = Path(done.stdout.strip().splitlines()[-1]) / "assets"
    shutil.rmtree(graphs / "viewer", ignore_errors=True)
    shutil.copytree(assets, graphs / "viewer")
    print(f"open /behavior/circuits/?slug={slug} in louped")
    return graphs
