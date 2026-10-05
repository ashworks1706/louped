"""A direction is one safetensors file under <home>/vectors, its provenance in the file's header.

One file per direction means a vector can be copied between machines or attached to a paper
without a database, and the Vectors page, the Playground and an eval all load it by name. Listing
them is `louped.stores.list_vectors`, which reads the headers without torch.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import torch
from safetensors import safe_open
from safetensors.torch import save_file

from louped.core import Direction, vectors_dir

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _path(name: str):
    if not _NAME.match(name):
        raise ValueError(f"bad vector name {name!r}: letters, digits, . _ - only")
    return vectors_dir() / f"{name}.safetensors"


def diff_in_means(positive: torch.Tensor, negative: torch.Tensor) -> torch.Tensor:
    """Mean of positive minus mean of negative, over the first axis, in float32."""
    return positive.float().mean(0) - negative.float().mean(0)


def save_vector(
    name: str,
    vector: torch.Tensor,
    *,
    model: str,
    layer: int,
    method: str,
    run: str | None = None,
    notes: str | None = None,
) -> Direction:
    v = vector.detach().float().cpu().contiguous()
    meta = Direction(
        name=name,
        model=model,
        layer=layer,
        method=method,
        norm=float(v.norm()),
        dim=v.numel(),
        created=datetime.now(UTC),
        run=run,
        notes=notes,
    )
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_file({"vector": v}, str(path), metadata={"louped": meta.model_dump_json()})
    return meta


def load_vector(name: str) -> tuple[torch.Tensor, Direction]:
    path = _path(name)
    if not path.exists():
        raise FileNotFoundError(f"no vector named {name!r} in {vectors_dir()}")
    with safe_open(str(path), framework="pt") as f:
        meta = Direction.model_validate_json(f.metadata()["louped"])
        return f.get_tensor("vector"), meta


def similarity(names: list[str]) -> list[list[float | None]]:
    """Cosine similarity between saved directions, row by row as named; None where two differ in
    size and cannot be compared."""
    vs = [load_vector(n)[0].flatten() for n in names]

    def cos(a: torch.Tensor, b: torch.Tensor) -> float | None:
        if a.numel() != b.numel():
            return None
        return float(torch.nn.functional.cosine_similarity(a, b, dim=0))

    return [[cos(a, b) for b in vs] for a in vs]
