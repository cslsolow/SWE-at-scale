"""Parsing, validation, and safe application of single-file patches."""

from __future__ import annotations

import difflib
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath


TAG_RE = re.compile(r"<\s*(?P<tag>[A-Za-z_][\w-]*)\s*>(.*?)<\s*/\s*(?P=tag)\s*>", re.I | re.S)


def extract_single_tag(text: str, tag: str) -> tuple[str, dict[str, object]]:
    matches = [m.group(2).strip() for m in TAG_RE.finditer(text) if m.group("tag").lower() == tag.lower()]
    if not matches:
        return "", {"status": f"missing_{tag}", "count": 0}
    if len(matches) > 1:
        return matches[0], {"status": f"duplicate_{tag}", "count": len(matches)}
    return matches[0], {"status": "ok", "count": 1}


def numbered_context(source: str) -> str:
    lines = source.splitlines()
    width = max(4, len(str(max(1, len(lines)))))
    return "\n".join(f"{idx:0{width}d} | {line}" for idx, line in enumerate(lines, 1))


def _normalize_path(raw: str) -> str | None:
    value = raw.strip().split("\t", 1)[0]
    if value == "/dev/null":
        return None
    if value.startswith(("a/", "b/")):
        value = value[2:]
    path = PurePosixPath(value)
    if value.startswith("/") or ".." in path.parts or not value or str(path) == ".":
        return None
    return str(path)


def changed_paths(patch: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for line in patch.splitlines():
        candidate: str | None = None
        if line.startswith("+++ "):
            candidate = _normalize_path(line[4:])
        elif line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                candidate = _normalize_path(parts[3])
        if candidate and candidate not in seen:
            seen.add(candidate)
            paths.append(candidate)
    return paths


def patch_stats(patch: str) -> dict[str, int]:
    added = removed = hunks = 0
    for line in patch.splitlines():
        if line.startswith("@@ "):
            hunks += 1
        elif line.startswith("+") and not line.startswith("+++ "):
            added += 1
        elif line.startswith("-") and not line.startswith("--- "):
            removed += 1
    return {"added_lines": added, "removed_lines": removed, "hunks": hunks}


def make_unified_diff(file_name: str, original: str, modified: str) -> str:
    """Create a single-file unified diff with stable relative paths."""
    lines = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=f"a/{file_name}",
            tofile=f"b/{file_name}",
            lineterm="",
        )
    )
    if not lines:
        return ""
    return "".join(line if line.endswith("\n") else line + "\n" for line in lines)


def _run_apply(root: Path, patch_path: Path, *, reverse: bool, recount: bool) -> tuple[bool, str]:
    command = ["git", "apply", "--whitespace=nowarn"]
    if recount:
        command.append("--recount")
    if reverse:
        command.append("--reverse")
    command.append(str(patch_path))
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=60)
    return result.returncode == 0, (result.stderr or result.stdout).strip()


def apply_patch_safely(file_name: str, original: str, patch: str) -> tuple[bool, str, dict[str, object]]:
    """Apply a patch, retrying with ``git apply --recount`` when necessary.

    The patch is required to touch exactly ``file_name``. A reverse-apply
    roundtrip is checked in a separate temporary directory before success is
    returned. No caller-controlled absolute path is ever used as a working
    directory target.
    """
    expected = _normalize_path(file_name)
    paths = changed_paths(patch)
    details: dict[str, object] = {"changed_paths": paths, "patch_stats": patch_stats(patch)}
    if expected is None:
        return False, "invalid_target_file_name", details
    if paths != [expected]:
        return False, f"patch_must_touch_only_target:{paths!r}", details
    if not patch.strip():
        return False, "empty_patch", details

    with tempfile.TemporaryDirectory(prefix="swe_at_scale_apply_") as temp:
        root = Path(temp)
        target = root / expected
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(original, encoding="utf-8")
        patch_path = root / ".swe_at_scale.patch"
        patch_path.write_text(patch, encoding="utf-8")
        applied, first_error = _run_apply(root, patch_path, reverse=False, recount=False)
        if applied:
            details["apply_mode"] = "git_apply"
        else:
            details["initial_apply_error"] = first_error
            applied, recount_error = _run_apply(root, patch_path, reverse=False, recount=True)
            details["recount_apply_error"] = recount_error
            if applied:
                details["apply_mode"] = "git_apply_recount"
        if not applied:
            return False, "forward_apply_failed", details
        modified = target.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="swe_at_scale_roundtrip_") as temp:
        root = Path(temp)
        target = root / expected
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(modified, encoding="utf-8")
        patch_path = root / ".swe_at_scale.patch"
        patch_path.write_text(patch, encoding="utf-8")
        reversed_ok, reverse_error = _run_apply(root, patch_path, reverse=True, recount=False)
        if not reversed_ok:
            reversed_ok, reverse_error = _run_apply(root, patch_path, reverse=True, recount=True)
        details["reverse_apply_success"] = reversed_ok
        if not reversed_ok:
            details["reverse_apply_error"] = reverse_error
            return False, "reverse_apply_failed", details
        if target.read_text(encoding="utf-8") != original:
            return False, "reverse_roundtrip_mismatch", details
    return True, modified, details
