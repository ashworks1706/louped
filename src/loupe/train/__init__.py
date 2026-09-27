"""Post-training recipes on TRL and PEFT, logged as MLflow runs. Needs the train extra."""

from loupe.train.sft import SftConfig, SftPlan, load_config, plan, train

__all__ = ["SftConfig", "SftPlan", "load_config", "plan", "train"]
