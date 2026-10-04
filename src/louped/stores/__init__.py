"""Read-only views over the stores other tools write: Inspect logs, MLflow, experiments/, graphs.

Each view is empty until its tool has written something, so the server answers with whatever
exists. Needs the server extra, which installs both readers.
"""

from louped.stores.compare import compare
from louped.stores.experiments import BadExperiment, get_experiment, list_experiments
from louped.stores.graphs import list_graphs
from louped.stores.labels import agreement, get_labels, set_label
from louped.stores.runs import (
    NotFound,
    get_feature,
    get_run,
    get_sample,
    list_features,
    list_runs,
    list_samples,
    list_views,
)
from louped.stores.vectors import list_vectors

__all__ = [
    "BadExperiment",
    "NotFound",
    "agreement",
    "compare",
    "get_experiment",
    "get_feature",
    "get_labels",
    "get_run",
    "get_sample",
    "list_experiments",
    "list_features",
    "list_graphs",
    "list_runs",
    "list_samples",
    "list_vectors",
    "list_views",
    "set_label",
]
