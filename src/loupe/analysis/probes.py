"""Linear probes: at which layer a label can be read off the residual stream by a linear map."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from nnsight import LanguageModel
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from loupe.analysis.activations import last_token_resid
from loupe.analysis.views import line


def linear_probes(
    lm: LanguageModel, prompts: list[str], labels: list[int], seed: int = 0
) -> tuple[list[float], torch.Tensor, dict[str, Any]]:
    """A logistic-regression probe per layer on the standardised last-token residual, scored on a
    held-out 25%.

    Labels are 0 or 1. Returns held-out accuracy by layer, each probe's unit weight vector
    [layers, hidden] pointing toward label 1, and the accuracy as a line view. A weight vector is a
    direction like any other: save it with loupe.vectors.save_vector to steer or ablate it.
    """
    y = np.asarray(labels)
    train, test = train_test_split(np.arange(len(y)), test_size=0.25, random_state=seed, stratify=y)
    accuracy: list[float] = []
    weights: list[torch.Tensor] = []
    for h in last_token_resid(lm, prompts).numpy():
        scaler = StandardScaler().fit(h[train])
        probe = LogisticRegression(max_iter=2000).fit(scaler.transform(h[train]), y[train])
        accuracy.append(float(probe.score(scaler.transform(h[test]), y[test])))
        w = torch.from_numpy(probe.coef_[0] / scaler.scale_).float()  # back in residual units
        weights.append(w / w.norm())
    chance = max(np.mean(y[test]), 1 - np.mean(y[test]))
    note = f"{len(test)} held-out of {len(y)} prompts; majority class {chance:.2f}"
    view = line("Linear probe accuracy by layer", x=[float(i) for i in range(len(accuracy))],
                series={"held-out accuracy": accuracy}, x_label="layer", y_label="accuracy",
                note=note, about="A linear classifier trained on each layer's activations. "
                "Accuracy above the majority class means that layer encodes the concept.",
                )  # fmt: skip
    return accuracy, torch.stack(weights), view
