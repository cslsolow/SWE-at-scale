from pathlib import Path

from swe_at_scale.api import Generation
from swe_at_scale.task_plan import run as run_task_plan


class FakeClient:
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def complete(self, messages, *, temperature, max_tokens):
        return Generation(content=next(self.outputs), raw=None)


def test_task_plan_and_executor_outputs_patch(tmp_path: Path):
    source_path = tmp_path / "input.py"
    source_path.write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    planner_output = (
        "<task_plan>Change the arithmetic behavior in f.</task_plan>\n"
        "<problem_statement>The result is incorrect for callers.</problem_statement>"
    )
    modified = "def f(x):\n    return x + 2\n"
    executor_output = f"<modified_file>{modified}</modified_file>"
    planner = FakeClient([planner_output])
    executor = FakeClient([executor_output])

    # Use a tiny factory-like shim so the test does not make network calls.
    import swe_at_scale.task_plan as module

    clients = iter([planner, executor])
    original_client = module.ChatClient
    module.ChatClient = lambda **kwargs: next(clients)
    try:
        result = run_task_plan(
            source_path,
            tmp_path / "out",
            planner_model="planner",
            executor_model="executor",
            planner_api_key="test",
            executor_api_key="test",
        )
    finally:
        module.ChatClient = original_client

    assert result["status"] == "ok"
    assert (tmp_path / "out" / "injection.patch").exists()
    assert (tmp_path / "out" / "injected_file").read_text() == modified
    assert "input.py" == result["target_file"]
