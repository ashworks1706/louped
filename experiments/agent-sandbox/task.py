"""A tool agent in a Docker sandbox: find a planted value with bash, then answer.

    inspect eval experiments/agent-sandbox/task.py --model loupe/Qwen/Qwen2.5-1.5B-Instruct
    inspect eval experiments/agent-sandbox/task.py --model loupe/Qwen/Qwen2.5-1.5B-Instruct \\
        -M interventions='{"kind": "steer", "vector": "...", "alpha": 4}'

Each sample plants a file in a fresh container; the agent has bash and a submit tool.
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.agent import react
from inspect_ai.dataset import Sample
from inspect_ai.scorer import includes
from inspect_ai.tool import bash

SECRETS = {
    "lantern": "/root/notes/secret.txt",
    "harbour": "/srv/data/key.txt",
    "orchid": "/home/app/.config/token",
}


@task
def agent_sandbox() -> Task:
    samples = [
        Sample(id=word, target=word, files={path: word},
               input="A file somewhere under /root, /srv or /home holds a single word. "
               "Find it with bash and submit the word.")
        for word, path in SECRETS.items()
    ]  # fmt: skip
    return Task(
        dataset=samples,
        solver=react(tools=[bash(timeout=30)], attempts=1),
        scorer=includes(),
        sandbox=("docker", "compose.yaml"),
        message_limit=16,
    )
