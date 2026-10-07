"""Alarms for a training run that looks degenerate, read from the numbers the trainer logs.

Both rules look only at the early window: the first max(EARLY_STEPS, EARLY_SHARE of the planned
steps) steps. A healthy run is still learning there; one that is already done has found a shortcut
in its data (a chosen reply copied from the prompt, a length cue).

- loss: the loss falls below max(LOSS_FLOOR, LOSS_SHARE x the first logged loss). DPO starts near
  ln 2 = 0.69, so the line is 0.0069; SFT starts near 2, so it is about 0.02.
- accuracy (DPO): rewards/accuracies is 1.0 on ACCURACY_RUN logs in a row: the chosen reply wins
  every pair of every batch.

An alarm is printed and joined into the run's louped.alarm tag with its step. Training goes on.
"""

from __future__ import annotations

import math
from typing import Any

EARLY_STEPS = 50
EARLY_SHARE = 0.1
LOSS_FLOOR = 0.001
LOSS_SHARE = 0.01
ACCURACY_RUN = 3
TAG = "louped.alarm"


class Alarms:
    """The rules above over a run's logs, in step order; each rule raises once."""

    def __init__(self, max_steps: int, raised: list[str] | None = None) -> None:
        self.window = max(EARLY_STEPS, math.ceil(EARLY_SHARE * max_steps))
        self.raised = list(raised or [])
        self._first_loss: float | None = None
        self._perfect = 0
        self._fired: set[str] = set()

    def see(self, step: int, logs: dict[str, Any]) -> list[str]:
        """The alarms this log raises."""
        new: list[str] = []
        loss = logs.get("loss")
        if isinstance(loss, int | float):
            if self._first_loss is None:
                self._first_loss = float(loss)
            line = max(LOSS_FLOOR, LOSS_SHARE * self._first_loss)
            if step <= self.window and loss < line and "loss" not in self._fired:
                self._fired.add("loss")
                new.append(f"loss {loss:.2g} below {line:.2g} at step {step} "
                           f"(started at {self._first_loss:.3g})")  # fmt: skip
        accuracy = logs.get("rewards/accuracies")
        if isinstance(accuracy, int | float):
            self._perfect = self._perfect + 1 if accuracy >= 1.0 else 0
            if step <= self.window and self._perfect >= ACCURACY_RUN and "acc" not in self._fired:
                self._fired.add("acc")
                new.append(f"rewards/accuracies 1.0 on {ACCURACY_RUN} logs in a row "
                           f"at step {step}")  # fmt: skip
        self.raised += new
        return new


def callback(raised: list[str]) -> Any:
    """A transformers TrainerCallback that runs the alarms inside the active MLflow run; raised
    are alarms known before training (the data's warnings)."""
    import mlflow
    from transformers import TrainerCallback

    class AlarmCallback(TrainerCallback):
        def on_train_begin(self, args, state, control, **kwargs):
            self.alarms = Alarms(state.max_steps, raised)

        def on_log(self, args, state, control, logs=None, **kwargs):
            for text in self.alarms.see(state.global_step, logs or {}):
                print(f"alarm: {text}")
                mlflow.set_tag(TAG, "; ".join(self.alarms.raised))

    return AlarmCallback()
