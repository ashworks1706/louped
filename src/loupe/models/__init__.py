"""Loading a model for interpretability: an nnsight LanguageModel over the real HF weights."""

from loupe.models.load import (
    attention,
    blocks,
    chat,
    final_norm,
    load,
    n_heads,
    n_layers,
    out_proj,
)

__all__ = ["attention", "blocks", "chat", "final_norm", "load", "n_heads", "n_layers", "out_proj"]
