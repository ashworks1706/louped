---
name: new-experiment
description: Start a research experiment in loupe. Use when the user wants to test an idea, run a study, or reproduce a paper.
---

1. Name the folder for the question, kebab-case: `just new-experiment <name>`.
2. Fill `experiments/<name>/README.md` before writing code:
   - **Question**: one sentence that can come out yes or no, or as a number.
   - **What would answer it**: the metric, the conditions compared, and the result that would
     change your mind. Name correctness and behaviour metrics separately; never average them.
3. Write `run.py` using existing tools first (nnsight, Inspect, TRL) and `loupe` where it has the
   piece. Write results under `.loupe/`, with `loupe.core.capture(seed=...).write(...)` next to them.
4. Pin what moves numbers: model revision, seed, greedy decoding unless sampling is the point.
5. If you write something a previous experiment also wrote, stop and move it into `src/loupe`
   instead (with a test), then use it from both.
6. Put the result in the README's **Result** section with the numbers and where the run lives.
