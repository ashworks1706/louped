"""Analyses over a model's activations. Each returns plain data and UI views."""

from loupe.analysis.activations import last_token_resid, positions, resid, token_strings
from loupe.analysis.attention import attention_patterns
from loupe.analysis.dynamics import checkpoints, model_diff, over_checkpoints
from loupe.analysis.lens import logit_lens
from loupe.analysis.patching import attribution_patch, patch_residual
from loupe.analysis.probes import linear_probes
from loupe.analysis.project import along, projection, top_examples
from loupe.analysis.sae import feature_examples, sae_features, save_feature
from loupe.analysis.splice import splice_divergence
from loupe.analysis.views import heatmap, line, table, token_row, tokens

__all__ = [
    "along",
    "attention_patterns",
    "attribution_patch",
    "checkpoints",
    "feature_examples",
    "heatmap",
    "last_token_resid",
    "line",
    "linear_probes",
    "logit_lens",
    "model_diff",
    "over_checkpoints",
    "patch_residual",
    "positions",
    "projection",
    "resid",
    "sae_features",
    "save_feature",
    "splice_divergence",
    "table",
    "token_row",
    "token_strings",
    "tokens",
    "top_examples",
]
