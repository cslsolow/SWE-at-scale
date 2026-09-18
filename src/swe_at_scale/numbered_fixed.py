"""SWE-at-scale direct inference pipeline."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from .api import ChatClient
from .patches import apply_patch_safely, extract_single_tag, numbered_context, patch_stats


SYSTEM_PROMPT = """You are an expert software engineer who creates realistic SWE-style issue patches.

Given a correct single-file implementation with line numbers for reference, introduce one realistic multi-hunk issue into that file. The issue should require coordinated edits in multiple related locations and should resemble a plausible software-engineering regression, incomplete feature behavior, API mismatch, boundary-condition bug, or security hardening regression.

Return exactly one <issue_patch>...</issue_patch> block containing a unified diff that transforms the fixed file into the issue-state file. The line numbers are references only: the patch must apply to the original file content without line-number prefixes. Do not return the complete file, a task plan, an explanation, markdown fences, or extra text."""

TASK_PROMPT = """Create one realistic multi-hunk issue in this single file.

Return a unified diff in <issue_patch>...</issue_patch>. Keep the patch limited to the target file and preserve syntactic validity."""


def safe_display_name(file_name: str) -> str:
    """Return a repository-relative display name without local path leakage."""
    raw = file_name.replace("\\", "/")
    path = PurePosixPath(raw)
    if raw.startswith("/") or ".." in path.parts:
        return path.name or "target.py"
    return str(path)


def build_messages(file_name: str, source: str) -> list[dict[str, str]]:
    display_name = safe_display_name(file_name)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f'<fixed_context path="{display_name}" line_numbered="true">\n'
                f"{numbered_context(source)}\n"
                "</fixed_context>\n\n"
                f"<task>\n{TASK_PROMPT}\n</task>"
            ),
        },
    ]


def run(
    input_file: Path,
    output_dir: Path,
    *,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 16_384,
    timeout: float = 1_800.0,
    api_retries: int = 3,
    client: ChatClient | None = None,
) -> dict[str, object]:
    source = input_file.read_text(encoding="utf-8")
    display_name = safe_display_name(input_file.name)
    messages = build_messages(display_name, source)
    client = client or ChatClient(
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=api_retries,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "messages.json").write_text(
        json.dumps({"messages": messages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        generation = client.complete(messages, temperature=temperature, max_tokens=max_tokens)
        raw_output = generation.content
        (output_dir / "model_raw_output.txt").write_text(raw_output, encoding="utf-8")
        patch, parse = extract_single_tag(raw_output, "issue_patch")
        if patch:
            # Tag extraction strips surrounding whitespace; restore the final
            # newline required by git's patch parser.
            patch = patch.rstrip("\n") + "\n"
        if parse["status"] != "ok":
            result = {
                "mode": "numbered_fixed",
                "target_file": display_name,
                "model": model,
                "status": parse["status"],
                "parse": parse,
                "patch_applied": False,
            }
            (output_dir / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            return result
        applied, modified_or_error, details = apply_patch_safely(display_name, source, patch)
        result: dict[str, object] = {
            "mode": "numbered_fixed",
            "target_file": display_name,
            "model": model,
            "status": "ok" if applied else "patch_rejected",
            "parse": parse,
            "patch_applied": applied,
            "patch_stats": patch_stats(patch),
            "patch_apply_details": details,
        }
        if applied:
            modified = str(modified_or_error)
            (output_dir / "injected_file").write_text(modified, encoding="utf-8")
            (output_dir / "injection.patch").write_text(patch, encoding="utf-8")
            result["injected_file"] = "injected_file"
            result["patch"] = "injection.patch"
        else:
            result["error"] = str(modified_or_error)
        (output_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return result
    except Exception as exc:
        result = {
            "mode": "numbered_fixed",
            "target_file": display_name,
            "model": model,
            "status": "generation_error",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "patch_applied": False,
        }
        (output_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return result
