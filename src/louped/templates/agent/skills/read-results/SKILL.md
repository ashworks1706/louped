---
name: read-results
description: Read a louped run's results and report them honestly. Use after a run finishes, or when the user asks what a run or experiment found.
---

1. Find the run: `runs` (filter by experiment), then `run <id>` for its metrics, parameters and
   files.
2. Read the files the run wrote: `report.md` first, then per-item records. For an eval, `samples`
   and `sample` give each transcript and score.
3. Before any number, say what it rests on: the denominator, which items, which model revision.
   A rate on fewer than ~30 items is a pilot; say so.
4. Compare two runs only with `compare <a> <b>`: report the difference with its paired interval
   and the run ids. Two runs on different items are not compared.
5. Read examples, not only rates: name at least one item where the behaviour happened and one
   where it did not, from the records, and check the scoring on them.
6. Separate what the result shows from what it suggests. Do not call a pilot result a finding or
   infer intent from an answer. Point the user to the run page (Items tab) for the rest, and write
   any report with `write-report`.
