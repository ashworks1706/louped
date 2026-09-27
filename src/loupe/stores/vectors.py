"""Saved directions, read from the safetensors headers without loading torch.

The format is an 8-byte little-endian header length, then a JSON header whose __metadata__ holds
the Direction under "loupe". Reading it directly keeps the server free of the interp extra.
"""

from __future__ import annotations

import json
import struct

from pydantic import ValidationError

from loupe.core import Direction, vectors_dir


def _header(path) -> dict:
    with open(path, "rb") as f:
        (length,) = struct.unpack("<Q", f.read(8))
        return json.loads(f.read(length))


def list_vectors() -> list[Direction]:
    root = vectors_dir()
    found: list[Direction] = []
    for path in sorted(root.glob("*.safetensors")) if root.is_dir() else []:
        try:
            meta = _header(path).get("__metadata__", {}).get("loupe")
            if meta:
                found.append(Direction.model_validate_json(meta))
        except (OSError, ValueError, struct.error, ValidationError):
            continue
    return sorted(found, key=lambda d: d.created, reverse=True)
