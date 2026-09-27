"""Group relative policy optimisation with LoRA: sample several replies per prompt, score each
with plain check functions (loupe.train.rewards), and move towards the better ones.

A row is {"prompt": [messages], ...}: any other field (an answer, a test) is passed to the checks
by name. Rewards are listed in the YAML as file.py:function, relative to the YAML file, so an
experiment's eval scorer and its training reward are the same function.

Multi-turn agents: `environment: file.py:Class` names a TRL environment. Each rollout gets its own
instance; `reset(**row)` starts it, its public methods are the tools the model calls between turns,
and an optional `get_reward()` scores the finished episode alongside the checks.

Every logging step's rollouts are kept (TRL's completions/ parquet files); the run gets a Rollouts
figure with the first and last logged steps, best and worst first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from loupe.train.base import TrainConfig, TrainError, fit, read_rows
from loupe.train.base import load_config as _load_config
from loupe.train.rewards import as_reward, load_check, load_object


class GrpoConfig(TrainConfig):
    """A grpo YAML file."""

    rewards: list[str] = Field(default_factory=list)
    #: A TRL environment class, file.py:Class: tools, per-rollout state and an optional reward.
    environment: str | None = None
    #: The most tool calls a rollout may make; None is no limit but the completion length.
    max_tool_turns: int | None = 8
    num_generations: int = 8
    max_completion_length: int = 256
    temperature: float = 1.0
    beta: float = 0.0
    _base_dir: Path | None = PrivateAttr(None)

    @model_validator(mode="after")
    def _groups_fit(self) -> GrpoConfig:
        if not self.rewards and not self.environment:
            raise ValueError("no reward: list rewards, or an environment with get_reward")
        batch = self.train.per_device_batch_size * self.train.gradient_accumulation
        if batch % self.num_generations:
            raise ValueError(
                f"per_device_batch_size * gradient_accumulation ({batch}) must be a multiple of "
                f"num_generations ({self.num_generations}): each prompt's group is one batch"
            )
        return self


class GrpoPlan(BaseModel):
    name: str
    base_model: str
    prompts: int
    rewards: list[str]
    environment: str | None
    tools: list[str]
    num_generations: int


class Prompt(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt: list[dict[str, Any]]


def load_config(path: Path) -> GrpoConfig:
    """The config; rewards named by a relative file resolve against the YAML file's folder."""
    cfg = _load_config(path, GrpoConfig)
    cfg._base_dir = path.parent
    return cfg


def plan(cfg: GrpoConfig) -> GrpoPlan:
    """What a run would do, without loading a model; also loads each reward, to fail early."""
    for spec in cfg.rewards:
        load_check(spec, cfg._base_dir)
    return GrpoPlan(name=cfg.name, base_model=cfg.base_model,
                    prompts=len(read_rows(cfg, Prompt)), rewards=cfg.rewards,
                    environment=cfg.environment, tools=tools(_environment(cfg)),
                    num_generations=cfg.num_generations)  # fmt: skip


def _environment(cfg: GrpoConfig) -> Any:
    if cfg.environment is None:
        return None
    env = load_object(cfg.environment, cfg._base_dir)
    if not callable(getattr(env, "reset", None)):
        raise TrainError(f"{cfg.environment}: an environment needs a reset method")
    return env


def tools(env: Any) -> list[str]:
    """The tools an environment class gives: its public methods but reset and get_reward.

    Only the class's own and its bases' methods, not attributes other libraries add to object.
    """
    if env is None:
        return []
    names = {n for cls in env.__mro__[:-1] for n, v in vars(cls).items() if callable(v)}
    return sorted(n for n in names if not n.startswith("_") and n not in ("reset", "get_reward"))


def _declared_only(env: Any) -> Any:
    """The environment class, listing only its own methods to TRL, which collects tools from dir().

    nnsight adds save() to every object once a trace has saved a value, which would become a tool.
    """
    names = [*tools(env), *(n for n in ("reset", "get_reward") if hasattr(env, n))]
    return type(env.__name__, (env,), {"__dir__": lambda self: names})


def train(cfg: GrpoConfig) -> Path:
    """Run GRPO; returns the adapter directory."""
    from datasets import Dataset
    from trl.trainer.grpo_config import GRPOConfig
    from trl.trainer.grpo_trainer import GRPOTrainer

    rewards: list[Any] = [as_reward(load_check(spec, cfg._base_dir)) for spec in cfg.rewards]
    env = _environment(cfg)
    rows = [p.model_dump() for p in read_rows(cfg, Prompt)]
    for old in (cfg.output_dir / "completions").glob("*.parquet"):
        old.unlink()

    def make(model: Any, tok: Any, peft: Any, args: dict[str, Any]) -> Any:
        extra: dict[str, Any] = {}
        if env is not None:
            from trl.chat_template_utils import add_response_schema

            if getattr(tok, "response_template", None) is None:
                add_response_schema(tok)
            extra["environment_factory"] = _declared_only(env)
        config = GRPOConfig(**args, beta=cfg.beta, num_generations=cfg.num_generations,
                            max_completion_length=cfg.max_completion_length,
                            temperature=cfg.temperature, log_completions=True,
                            num_completions_to_print=0,
                            max_tool_calling_iterations=cfg.max_tool_turns)  # fmt: skip
        return GRPOTrainer(model=model, processing_class=tok, peft_config=peft,
                           reward_funcs=rewards, train_dataset=Dataset.from_list(rows),
                           args=config, **extra)  # fmt: skip

    return fit(cfg, "grpo", len(rows), make, after=_log_rollouts)


def _log_rollouts(cfg: TrainConfig) -> None:
    """The first and last logged steps' rollouts as a table figure on the active run."""
    import pandas as pd

    from loupe.analysis.views import table
    from loupe.tracking import log_json

    files = sorted((cfg.output_dir / "completions").glob("completions_*.parquet"))
    if not files:
        return
    frames = [pd.read_parquet(f) for f in dict.fromkeys([files[0], files[-1]])]
    rollouts = pd.concat(frames, ignore_index=True)
    rewards = [
        c for c in rollouts.columns if c not in ("step", "prompt", "completion", "advantage")
    ]
    rollouts["reward"] = rollouts[rewards].fillna(0).sum(axis=1) if rewards else 0.0
    rollouts = rollouts.sort_values(["step", "reward"], ascending=[True, False])
    columns = ["step", "reward", "advantage", *rewards, "completion"]
    rows = [[_cell(r[c]) for c in columns] for _, r in rollouts.iterrows()]
    note = f"{len(files)} logged steps; all under {cfg.output_dir / 'completions'}"
    log_json(table("Rollouts", columns, rows, note=note), "views/rollouts.json")


def _cell(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    return value if isinstance(value, int | str) else str(value)
