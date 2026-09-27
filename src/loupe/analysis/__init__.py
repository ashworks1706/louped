"""Analyses over a model's activations. Each returns plain data: tensors or UI views."""

from loupe.analysis.activations import last_token_resid
from loupe.analysis.lens import logit_lens
from loupe.analysis.patching import patch_residual
from loupe.analysis.views import heatmap, line, table

__all__ = ["heatmap", "last_token_resid", "line", "logit_lens", "patch_residual", "table"]
