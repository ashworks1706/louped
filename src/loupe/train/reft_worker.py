"""The ReFT training worker, run by `loupe train reft` in pyreft's own environment (uvx). It
imports nothing from loupe: the job comes in as JSON, the loss goes out as metrics.jsonl, the test
replies as replies.json, and the intervention is saved under <out>/reft.

    python reft_worker.py job.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pyreft
import torch
import transformers


def main(path: str) -> None:
    job = json.loads(Path(path).read_text())
    out = Path(job["out"])
    torch.manual_seed(job["seed"])
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    tok = transformers.AutoTokenizer.from_pretrained(job["model"])
    tok.pad_token = tok.pad_token or tok.eos_token
    model = transformers.AutoModelForCausalLM.from_pretrained(job["model"], torch_dtype=dtype)
    model.to(device)

    hidden = model.config.hidden_size
    reps = [{"layer": layer, "component": "block_output", "low_rank_dimension": job["rank"],
             "intervention": pyreft.LoreftIntervention(embed_dim=hidden,
                                                       low_rank_dimension=job["rank"])}
            for layer in job["layers"]]  # fmt: skip
    reft = pyreft.get_reft_model(model, pyreft.ReftConfig(representations=reps))
    reft.set_device(device)

    def prompt(messages: list[dict]) -> str:
        return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    data = pyreft.make_last_position_supervised_data_module(
        tok, model, [prompt(e["messages"]) for e in job["train"]],
        [e["reply"] + tok.eos_token for e in job["train"]], num_interventions=len(reps),
    )  # fmt: skip
    metrics = (out / "metrics.jsonl").open("a")

    class Log(transformers.TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            keep = {k: v for k, v in (logs or {}).items() if isinstance(v, int | float)}
            metrics.write(json.dumps({"step": state.global_step, **keep}) + "\n")
            metrics.flush()

    args = transformers.TrainingArguments(
        output_dir=str(out / "trainer"), num_train_epochs=job["epochs"], max_steps=job["max_steps"],
        per_device_train_batch_size=job["per_device_batch_size"],
        learning_rate=job["learning_rate"], logging_steps=job["logging_steps"], seed=job["seed"],
        report_to=[], save_strategy="no",
    )  # fmt: skip
    trainer = pyreft.ReftTrainerForCausalLM(model=reft, tokenizer=tok, args=args,
                                            callbacks=[Log()], **data)  # fmt: skip
    trainer.train()

    rows = []
    for e in job["test"]:
        ids = tok(prompt(e["messages"]), return_tensors="pt").to(device)
        last = ids["input_ids"].shape[-1] - 1
        gen = {"max_new_tokens": job["max_new_tokens"], "do_sample": False,
               "eos_token_id": tok.eos_token_id}  # fmt: skip
        with torch.no_grad():
            base = model.generate(**ids, **gen)
            _, steered = reft.generate(ids, unit_locations={"sources->base": (
                None, [[[last]]] * len(reps))}, intervene_on_prompt=True, **gen)  # fmt: skip
        n = ids["input_ids"].shape[-1]
        rows.append({"prompt": e["messages"][-1]["content"], "target": e["reply"],
                     "base": tok.decode(base[0][n:], skip_special_tokens=True).strip(),
                     "reft": tok.decode(steered[0][n:],
                                        skip_special_tokens=True).strip()})  # fmt: skip
    (out / "replies.json").write_text(json.dumps(rows, indent=2))
    reft.set_device("cpu")
    reft.save(save_directory=str(out / "reft"))


if __name__ == "__main__":
    main(sys.argv[1])
