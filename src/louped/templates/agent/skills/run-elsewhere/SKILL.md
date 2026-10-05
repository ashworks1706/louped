---
name: run-elsewhere
description: Run a louped experiment on a Slurm cluster (such as ASU Sol) or a VM and bring the result back. Use when a model is too large for this machine or the user asks for a real run.
---

1. Run the experiment here first on a small setting (a tiny model or `--limit`), so the cluster's
   time goes to the real run.
2. Commit and push the experiment. A project that is a pushed git commit exports as one file,
   `louped-<id>.sh`, which clones that commit on the cluster. Otherwise the export is a
   `louped-<id>.tar.gz`, and the note returned with it says why.
3. Export it with the `export_job` MCP tool (or Launch, then "Run on" Sol / Slurm / VM, then
   Export). Pass the launchable id, the options and a target. Ask for one GPU unless the model
   needs more. Ask for enough hours to cover the first run's installs and downloads as well as the
   work.
4. You cannot reach the cluster, so tell the user exactly what to run:
   - Copy the file to the cluster's scratch.
   - On a login node, export `HF_TOKEN` (or run `hf auth login`). Gated models need it, and so
     does pushing to an `hf://` remote.
   - Run `sbatch louped-<id>.sh`, or `bash` on a VM. For a tarball, unpack it and run its
     `job.sh` the same way. Then follow the `.out` file.
5. Bring the result back:
   - **With a remote** (`remote` in louped.toml): the job pushes its own results. Call `pull` (or
     press Pull on Runs). Its runs then read like local ones, marked with the host.
   - **Without one**: the user brings back `louped-result-<id>.tar.gz`. Import it with
     `import_result <path>`.
6. Read the result with `read-results`. Write it up with `write-report`.
