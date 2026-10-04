# Security

Report vulnerabilities privately through GitHub's "Report a vulnerability" on this repository,
not in a public issue.

`louped serve` binds to 127.0.0.1 and has no authentication. Launching jobs and loading a model run
code on the machine, so they are on only for a loopback server. `--host` needs `--expose`, which
serves read-only: whoever reaches the port reads every run, log and transcript. Do not expose it on
a network you do not trust.
