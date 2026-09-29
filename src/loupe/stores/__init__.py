"""Read-only views over the stores other tools write: Inspect logs, MLflow, experiments/, graphs.

Each view is empty until its tool has written something, so the server answers with whatever
exists. Needs the server extra, which installs both readers.
"""

from loupe.stores.compare import compare
from loupe.stores.experiments import list_experiments
from loupe.stores.graphs import list_graphs
from loupe.stores.runs import (
    NotFound,
    get_feature,
    get_run,
    get_sample,
    list_features,
    list_runs,
    list_samples,
    list_views,
)
from loupe.stores.vectors import list_vectors

__all__ = [
    "NotFound",
    "compare",
    "get_feature",
    "get_run",
    "get_sample",
    "list_experiments",
    "list_features",
    "list_graphs",
    "list_runs",
    "list_samples",
    "list_vectors",
    "list_views",
]
