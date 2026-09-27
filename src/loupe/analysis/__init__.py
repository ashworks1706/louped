"""Analyses over a model's activations. Each returns plain data and UI views."""

from loupe.analysis.activations import last_token_resid, positions
from loupe.analysis.attention import attention_patterns
from loupe.analysis.lens import logit_lens
from loupe.analysis.patching import attribution_patch, patch_residual
from loupe.analysis.probes import linear_probes
from loupe.analysis.views import heatmap, line, table

__all__ = [
    "attention_patterns",
    "attribution_patch",
    "heatmap",
    "last_token_resid",
    "line",
    "linear_probes",
    "logit_lens",
    "patch_residual",
    "positions",
    "table",
]
