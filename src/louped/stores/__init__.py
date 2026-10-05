"""Views over the stores other tools write: Inspect logs, MLflow, experiments/, graphs. They only
read, but for a person's own words (labels, an experiment's README, a run's text files) and for
deleting an experiment or a run, which moves it to the trash rather than removing it.

Each view is empty until its tool has written something, so the server answers with whatever
exists. Needs the server extra, which installs both readers.
"""

from louped.stores.compare import compare
from louped.stores.experiments import (
    BadExperiment,
    delete_experiment,
    get_experiment,
    list_experiments,
    read_readme,
    write_readme,
)
from louped.stores.graphs import list_graphs
from louped.stores.items import CohortStats, cohort
from louped.stores.labels import agreement, get_labels, set_label
from louped.stores.runs import (
    NotFound,
    delete_run,
    get_feature,
    get_run,
    get_sample,
    list_features,
    list_runs,
    list_samples,
    list_views,
    write_text,
)
from louped.stores.vectors import list_vectors

__all__ = [
    "BadExperiment",
    "CohortStats",
    "NotFound",
    "agreement",
    "cohort",
    "compare",
    "delete_experiment",
    "delete_run",
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
    "read_readme",
    "set_label",
    "write_readme",
    "write_text",
]
