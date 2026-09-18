from pathlib import Path

from swe_at_scale.api import Generation
from swe_at_scale.numbered_fixed import run as run_numbered
from swe_at_scale.patches import apply_patch_safely, make_unified_diff


def test_unified_diff_applies_and_roundtrips():
    original = "def f(x):\n    return x + 1\n"
    modified = "def f(x):\n    return x + 2\n"
    patch = make_unified_diff("input.py", original, modified)
    ok, result, details = apply_patch_safely("input.py", original, patch)
    assert ok
    assert result == modified
    assert details["reverse_apply_success"] is True


def test_patch_rejects_unexpected_file():
    patch = """diff --git a/other.py b/other.py
--- a/other.py
+++ b/other.py
@@ -1 +1 @@
-x = 1
+x = 2
"""
    ok, error, _ = apply_patch_safely("input.py", "x = 1\n", patch)
    assert not ok
    assert "only_target" in error


class FakeClient:
    def __init__(self, content: str):
        self.content = content

    def complete(self, messages, *, temperature, max_tokens):
        return Generation(content=self.content, raw=None)


def test_numbered_pipeline_writes_relative_outputs(tmp_path: Path):
    source_path = tmp_path / "secret" / "input.py"
    source_path.parent.mkdir()
    source_path.write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    patch = """diff --git a/input.py b/input.py
--- a/input.py
+++ b/input.py
@@ -1,2 +1,2 @@
 def f(x):
-    return x + 1
+    return x + 2
"""
    result = run_numbered(
        source_path,
        tmp_path / "out",
        model="test-model",
        client=FakeClient(f"<issue_patch>\n{patch}</issue_patch>"),
    )
    assert result["status"] == "ok"
    assert result["target_file"] == "input.py"
    assert "secret" not in (tmp_path / "out" / "result.json").read_text()
