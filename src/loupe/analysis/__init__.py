"""Analyses over a model's activations. Each returns plain data and UI views."""

from loupe.analysis.activations import last_token_resid, positions, resid, token_strings
from loupe.analysis.attention import attention_patterns, attention_to_span
from loupe.analysis.dose import dose_response
from loupe.analysis.dynamics import checkpoints, model_diff, over_checkpoints
from loupe.analysis.lens import logit_lens
from loupe.analysis.patching import attribution_patch, patch_heads, patch_residual
from loupe.analysis.probes import linear_probes
from loupe.analysis.project import along, projection, top_examples
from loupe.analysis.sae import feature_dashboards, feature_examples, sae_features, save_feature
from loupe.analysis.speed import footprint, speed_view, timing
from loupe.analysis.splice import splice_divergence
from loupe.analysis.trajectory import trajectory
from loupe.analysis.views import by_head, heatmap, line, scatter, table, token_row, tokens

__all__ = [
    "along",
    "attention_patterns",
    "attention_to_span",
    "attribution_patch",
    "by_head",
    "checkpoints",
    "dose_response",
    "feature_dashboards",
    "feature_examples",
    "footprint",
    "heatmap",
    "last_token_resid",
    "line",
    "linear_probes",
    "logit_lens",
    "model_diff",
    "over_checkpoints",
    "patch_heads",
    "patch_residual",
    "positions",
    "projection",
    "resid",
    "sae_features",
    "save_feature",
    "scatter",
    "speed_view",
    "splice_divergence",
    "table",
    "timing",
    "token_row",
    "token_strings",
    "tokens",
    "top_examples",
    "trajectory",
]
