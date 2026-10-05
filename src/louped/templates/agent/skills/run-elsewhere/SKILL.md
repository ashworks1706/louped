---
name: run-elsewhere
description: Run a louped experiment on a Slurm cluster (such as ASU Sol) or a VM and bring the result back. Use when a model is too large for this machine or the person asks for a real run.
---

1. Run the experiment here first on a small setting (a tiny model or `--limit`). Thus the cluster's
   time goes to the real run.
2. Commit and push the experiment.
   - A project that is a pushed git commit exports as one file, `louped-<id>.sh`. This file clones
     that commit on the cluster.
   - Otherwise the export is a `louped-<id>.tar.gz`, and the note returned with it says why.
3. Export it with the `export_job` MCP tool. (In the app: Launch, then "Run on" Sol / Slurm / VM,
   then Export.)
   - Pass the launchable id, the options and a target.
   - Ask for one GPU, unless the model needs more.
   - Ask for the hours the work needs plus 1 hour for the first installs and downloads.
4. You cannot reach the cluster. Tell the person exactly what to run:
   1. Copy the file to the cluster's scratch.
   2. Once per cluster, run `hf auth login` on a login node (or export `HF_TOKEN`). Gated models
      need it, and so does pushing to an `hf://` remote. If that remote finds no token, the job
      stops before it runs.
   3. Run `sbatch louped-<id>.sh`, or `bash` on a VM. For a tarball, unpack it and run its
      `job.sh` the same way.
   4. Follow the `.out` file.
5. Bring the result back:
   - **With a remote** (`remote` in louped.toml): the job pushes its own results. Call `pull` (or
     press Pull on Runs). Its runs then read like local ones, marked with the host.
   - **To set up a remote** (if none is set): ask the person to press Connect on Runs, or to run `louped push` in a
     terminal. Either one sets up a private HF bucket and asks for their token. Never ask for the
     token in chat.
   - **Without a remote**: the person brings back `louped-result-<id>.tar.gz`. Import it with
     `import_result <path>`.
6. Read the result with `read-results`.
7. Write it up with `write-report`.
