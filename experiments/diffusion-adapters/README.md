# diffusion-adapters

## Question

On a masked diffusion LM, does a LoRA skill beat a prompt for the same skill? Do two skills trained
apart compose, live together or merged? Does routing them by phase of the denoising trajectory
(one skill over the early steps, the other over the late ones) do better than both at once?

## What would answer it

Two skills, fact (what is the sky: it is blue) and tone (please tell me a story: sure here is a
story), trained separately by the masked_diffusion sft recipe. A grid over three tasks, facts,
requests and both (please tell me what is the sky: sure it is blue, seen by neither skill), under
base, a few-shot prompt, each skill, both live, both merged (PEFT linear) and phase-routed (tone
over the first half of the steps, fact over the second, and the reverse as a control), each against
base with a paired interval:

- adapter beats prompt: fact on facts and tone on requests above prompt;
- skills compose: both or merged above each single skill on the both task;
- phase routing helps: routed above both and above reversed on the both task.

The sampler fills the reply in two blocks left to right, so the first half of the steps writes the
opening (tone's part) and the second the answer (fact's part). The analysis run logs the per-site
overlap of the two LoRAs and the denoising trajectory of one both-task prompt under every
condition (step by reply position, each cell the commit confidence, labelled with the reply so far).

Soft prompts are not a condition: the sft recipe trains them for causal LMs only.

## Run

```sh
uv run --extra train python experiments/diffusion-adapters/run.py --model GSAI-ML/LLaDA-8B-Instruct --revision <commit>
OMP_NUM_THREADS=1 uv run --extra train python experiments/diffusion-adapters/run.py --tiny   # offline, a few minutes
```

The two training runs, the analysis run (overlap, trajectories) and the grid appear under Runs;
the skills are kept under adapters as fact and tone.

## Result

Not run on a real model: LLaDA and Dream need more than a 6 GB GPU.

`--tiny` uses a random two-layer masked LM from loupe.models.tiny as the base; its numbers only
show the pipeline runs and are not evidence about real models. Both skills fit their own task
(accuracy 1.00 each, 0.00 on the other's, base and prompt 0.00 everywhere), and their deltas are
near orthogonal at every site (cosine within 0.08, 0.21 at the output layer). Nothing composes on
the both task: 0.00 under both, merged, routed and reversed. Both live keeps 0.71 of facts, merged
none; reversed (fact first) keeps facts at 1.00 because the answer sits in the first block.
