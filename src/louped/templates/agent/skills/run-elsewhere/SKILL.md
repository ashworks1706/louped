---
name: run-elsewhere
description: Run a louped experiment on a Slurm cluster (such as ASU Sol) or a VM and bring the result back. Use when a model is too large for this machine or the user asks for a real run.
---

1. Check the experiment runs here first on a small setting (a tiny model or `--limit`), so the
   cluster's time goes to the real run.
2. Export it: the `export_job` MCP tool (or Launch, then "Run on" Sol / Slurm / VM, then Export)
   with the launchable id, the options and a target. Ask for one GPU unless the model needs more,
   and hours that cover the first run's setup (installs and downloads) as well as the work.
3. Tell the user exactly what to run, since you cannot reach the cluster:
   - copy the folder to the cluster's scratch, and `cd` into it;
   - on a login node, set `HF_HOME` and `UV_CACHE_DIR` to scratch and run the job's install line
     once (the job then reuses the cache), and `hf auth login` with that `HF_HOME` for gated
     models;
   - `sbatch job.sh` (or `bash job.sh` on a VM), then follow the `.out` file.
4. When the user has the `louped-result-<id>.tar.gz`, import it with `import_result <path>` (or the
   Runs page's Import, or `louped import`). Its runs then read like local ones, marked with the host.
5. Read the result with `read-results`.
