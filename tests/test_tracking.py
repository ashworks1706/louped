"""A run samples the machine while it is open, as system/ metrics over time."""

import time

import pytest

from louped import stores
from louped.tracking import start_run


def test_a_run_records_the_machine_over_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOUPED_SYSTEM_METRICS", "1")
    monkeypatch.setattr("louped.tracking.runs.SAMPLE_SECONDS", 1)
    with start_run("telemetry") as run:
        time.sleep(2.5)
    detail = stores.get_run(f"m-{run.info.run_id}")
    assert "system/cpu_utilization_percentage" in detail.metrics
    assert len(detail.history["system/system_memory_usage_megabytes"]) >= 2


def test_off_means_no_system_metrics() -> None:
    with start_run("telemetry") as run:
        pass
    assert not [
        k for k in stores.get_run(f"m-{run.info.run_id}").metrics if k.startswith("system/")
    ]
