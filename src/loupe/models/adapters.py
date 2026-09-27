"""A bank of named PEFT adapters on one base model, any subset live at a time.

Every adapter stays a separate delta on the frozen base, so equipping a set is a switch, not a
reload: `activate(model, ["a", "b"])` sums both LoRA deltas (PEFT's multi-adapter forward),
`activate(model, [])` runs the bare base. `merge` builds a new adapter from several with PEFT's
own methods (linear, TIES, DARE, ...), for merging as a baseline against live composition.
Phases change the live set along one generation, through a per-step hook the samplers call.
Adapters are directories as PEFT saves them, found by name under <home>/adapters or by path.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from itertools import combinations
from pathlib import Path
from typing import Any

import torch
from pydantic import BaseModel

from loupe.core import adapters_dir


def adapter_path(name: str) -> Path:
    """<home>/adapters/<name> when it exists, else the name as a path."""
    local = adapters_dir() / name
    path = local if local.exists() else Path(name)
    if not (path / "adapter_config.json").exists():
        raise FileNotFoundError(f"no adapter {name!r} under {adapters_dir()} or at that path")
    return path


def bank(base: Any, names: Sequence[str]) -> Any:
    """The base model with every named adapter loaded beside the others, all inactive."""
    try:
        from peft import PeftModel
    except ImportError as exc:
        raise ImportError("an adapter bank needs the train extra: loupelab[train]") from exc
    if not names:
        raise ValueError("a bank needs at least one adapter")
    first, *rest = names
    model = PeftModel.from_pretrained(base, str(adapter_path(first)), adapter_name=first)
    for name in rest:
        model.load_adapter(str(adapter_path(name)), adapter_name=name)
    model.eval()
    activate(model, [])
    return model


def activate(model: Any, names: Sequence[str]) -> None:
    """Make exactly these adapters live in any module tree holding the bank's LoRA layers (the
    PeftModel or the HF model inside it), their deltas summed; none runs the bare base."""
    from peft.tuners.tuners_utils import BaseTunerLayer

    layers = [m for m in model.modules() if isinstance(m, BaseTunerLayer)]
    known = {a for m in layers for a in getattr(m, "lora_A", {})}
    missing = set(names) - known
    if missing:
        raise KeyError(f"not in the bank: {sorted(missing)}")
    for layer in layers:
        layer.enable_adapters(bool(names))
        if names:
            layer.set_adapter(list(names))
    for p in model.parameters():  # set_adapter marks the live ones trainable
        p.requires_grad_(False)


def merge(
    model: Any,
    names: Sequence[str],
    weights: Sequence[float] | None = None,
    method: str = "linear",
    density: float | None = None,
) -> str:
    """A new adapter in the bank merged from these (PEFT add_weighted_adapter); returns its name."""
    name = f"{method}:{'+'.join(names)}"
    if name not in model.peft_config:
        model.add_weighted_adapter(list(names), list(weights or [1.0] * len(names)), name,
                                   combination_type=method, density=density)  # fmt: skip
    return name


def subsets(names: Sequence[str]) -> dict[str, list[str]]:
    """Every subset of the adapters, smallest first, named a+b; the empty one is none."""
    out: dict[str, list[str]] = {"none": []}
    for size in range(1, len(names) + 1):
        for combo in combinations(names, size):
            out["+".join(combo)] = list(combo)
    return out


def overlap(model: Any) -> tuple[list[str], list[str], list[list[float]]]:
    """Per LoRA site, the cosine between each pair of adapters' weight deltas (B @ A): pairs, sites
    and a grid. Near zero means the skills write to different directions of that weight.
    """
    sites: dict[str, dict[str, torch.Tensor]] = {}
    for mod_name, module in model.named_modules():
        if hasattr(module, "lora_A") and hasattr(module, "lora_B"):
            for adapter in module.lora_A:
                delta = module.lora_B[adapter].weight @ module.lora_A[adapter].weight
                sites.setdefault(mod_name, {})[adapter] = delta.flatten().float()
    names = sorted({a for d in sites.values() for a in d})
    pairs = [(a, b) for a, b in combinations(names, 2)]
    grid = [[_cos(d.get(a), d.get(b)) for a, b in pairs] for d in sites.values()]
    return [f"{a} · {b}" for a, b in pairs], list(sites), grid


def _cos(a: torch.Tensor | None, b: torch.Tensor | None) -> float:
    if a is None or b is None or a.norm() == 0 or b.norm() == 0:
        return 0.0
    return float(torch.nn.functional.cosine_similarity(a, b, dim=0))


class Phase(BaseModel):
    """Adapters live over the fraction [start, end) of a generation: of the denoising steps for a
    masked diffusion model, of max_new_tokens for an autoregressive one. Overlaps add up."""

    start: float = 0.0
    end: float = 1.0
    adapters: list[str]


def split(early: str, late: str, at: float = 0.5) -> list[Phase]:
    """One adapter before the split point and another after it; split(b, a) is its reverse."""
    return [Phase(start=0.0, end=at, adapters=[early]), Phase(start=at, end=1.0, adapters=[late])]


def phase_hook(model: Any, phases: Sequence[Phase | dict[str, Any]]) -> Callable[[int, int], None]:
    """A per-step hook that makes the adapters of the phases covering step / steps live."""
    parsed = [Phase.model_validate(p) for p in phases]
    for p in parsed:
        if not 0.0 <= p.start < p.end <= 1.0:
            raise ValueError(f"phase [{p.start}, {p.end}) is not inside [0, 1)")

    def hook(step: int, steps: int) -> None:
        t = step / max(steps, 1)
        live = sorted({a for p in parsed if p.start <= t < p.end for a in p.adapters})
        activate(model, live)

    return hook
