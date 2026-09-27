"""A coding agent in a Docker sandbox: implement a function, scored by hidden unit tests.

    inspect eval experiments/coding-agent/task.py --model loupe/Qwen/Qwen2.5-1.5B-Instruct
    inspect eval experiments/coding-agent/task.py -T benchmark=humaneval --model openai-api/local/m

The agent is Inspect's react with bash and python in the container. The tests stay out of the
prompt; inspect_evals' HumanEval scorer runs them in the same container after submit. The builtin
problems use HumanEval's record format, so both benchmarks share the prompt and the scorer.
"""

from __future__ import annotations

from pathlib import Path

from inspect_ai import Task, task, task_with
from inspect_ai.agent import as_solver, react
from inspect_ai.tool import bash, python
from inspect_evals.humaneval import humaneval
from inspect_evals.humaneval.humaneval import record_to_sample, verify

from loupe.inspect_ext import called, grounded, tool_calls, tool_errors

INSTRUCTION = """Implement the function below. You have bash and python in a sandbox: run your
code against examples you write before you answer. Then submit the complete function source,
signature included, with the submit tool.

"""

PROBLEMS = [
    {
        "task_id": "builtin/0",
        "entry_point": "running_max",
        "prompt": '''def running_max(xs: list[int]) -> list[int]:
    """The largest value seen so far at each position: [1, 3, 2] -> [1, 3, 3]."""
''',
        "test": """def check(f):
    assert f([1, 3, 2]) == [1, 3, 3]
    assert f([]) == []
    assert f([-2, -5, 0]) == [-2, -2, 0]
""",
        "canonical_solution": """def running_max(xs):
    out, top = [], None
    for x in xs:
        top = x if top is None else max(top, x)
        out.append(top)
    return out
""",
    },
    {
        "task_id": "builtin/1",
        "entry_point": "balanced",
        "prompt": '''def balanced(s: str) -> bool:
    """Whether the brackets (), [] and {} in s are balanced; other characters are ignored."""
''',
        "test": """def check(f):
    assert f("a(b[c]{d})")
    assert not f("(]")
    assert not f("((")
    assert f("")
    assert not f(")(")
""",
        "canonical_solution": """def balanced(s):
    pairs, stack = {")": "(", "]": "[", "}": "{"}, []
    for c in s:
        if c in "([{":
            stack.append(c)
        elif c in pairs and (not stack or stack.pop() != pairs[c]):
            return False
    return not stack
""",
    },
    {
        "task_id": "builtin/2",
        "entry_point": "roman",
        "prompt": '''def roman(n: int) -> str:
    """n from 1 to 3999 as a Roman numeral: 1994 -> MCMXCIV."""
''',
        "test": """def check(f):
    assert f(1994) == "MCMXCIV"
    assert f(4) == "IV"
    assert f(3999) == "MMMCMXCIX"
    assert f(58) == "LVIII"
""",
        "canonical_solution": """def roman(n):
    values = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    out = ""
    for v, r in zip(values, "M CM D CD C XC L XL X IX V IV I".split()):
        out += r * (n // v)
        n %= v
    return out
""",
    },
    {
        "task_id": "builtin/3",
        "entry_point": "rle",
        "prompt": '''def rle(s: str) -> list[tuple[str, int]]:
    """Run-length encoding: aaab -> [(a, 3), (b, 1)] with each a one-character string."""
''',
        "test": """def check(f):
    assert f("aaab") == [("a", 3), ("b", 1)]
    assert f("") == []
    assert f("abba") == [("a", 1), ("b", 2), ("a", 1)]
""",
        "canonical_solution": """def rle(s):
    import itertools
    return [(k, len(list(g))) for k, g in itertools.groupby(s)]
""",
    },
]


@task
def coding_agent(benchmark: str = "builtin", message_limit: int = 20) -> Task:
    """benchmark is builtin (offline) or humaneval (downloads it from the Hugging Face Hub)."""
    agent = as_solver(react(tools=[bash(timeout=30), python(timeout=30)], attempts=1))
    scorers = [verify(), tool_calls(), tool_errors(), called("python"), grounded("python")]
    if benchmark == "humaneval":
        base = humaneval(solver=agent, instruction_prompt=INSTRUCTION, scorer=scorers)
    else:
        samples = [record_to_sample(INSTRUCTION)(p) for p in PROBLEMS]
        base = Task(dataset=samples, solver=agent, scorer=scorers, name="coding_agent")
    compose = str(Path(__file__).parent / "compose.yaml")
    return task_with(base, sandbox=("docker", compose), message_limit=message_limit)
