"""Stage 5 Task Plan plus executor inference pipeline."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from .api import ChatClient
from .patches import apply_patch_safely, extract_single_tag, make_unified_diff, patch_stats


PLANNER_SYSTEM_PROMPT = """You are an expert software engineer and benchmark-task designer.

Given correctly implemented code, design one realistic SWE-style task that can be created by modifying the code.

The <task_plan> is an implementation specification for a downstream code model. It must specify where and how the code should be modified, what behavior should be changed, and what failure should result. The downstream model should implement the plan, not decide what issue to inject.

The <problem_statement> should describe the resulting issue as a realistic software-engineering report without revealing the implementation change or fix.

Return exactly <task_plan>...</task_plan> and <problem_statement>...</problem_statement>. Do not write the actual code change, patch, diff, replacement code, or markdown fences."""

PLANNER_TASK_PROMPT = """Design one realistic SWE-style task for this single file.

Create an implementation-ready task plan for a downstream code model and a corresponding realistic problem statement."""

EXECUTOR_SYSTEM_PROMPT = """You are a precise code editing executor.

Modify the given fixed source code to implement the provided task plan. Do not choose a different task. Preserve unrelated behavior and formatting as much as practical.

Return exactly one <modified_file>...</modified_file> block containing the complete modified file. Do not return a patch, diff, markdown fence, explanation, or additional text."""

EXECUTOR_TASK_PROMPT = """Apply the task plan to the fixed code.

Return the complete modified file inside <modified_file>...</modified_file>, and nothing else."""


def safe_display_name(file_name: str) -> str:
    raw = file_name.replace("\\", "/")
    path = PurePosixPath(raw)
    if raw.startswith("/") or ".." in path.parts:
        return path.name or "target.py"
    return str(path)


def build_planner_messages(file_name: str, source: str) -> list[dict[str, str]]:
    display_name = safe_display_name(file_name)
    return [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f'<fixed_context path="{display_name}">\n{source}\n</fixed_context>\n\n'
                f"<task>\n{PLANNER_TASK_PROMPT}\n</task>"
            ),
        },
    ]


def build_executor_messages(
    file_name: str,
    source: str,
    task_plan: str,
    problem_statement: str = "",
    include_problem_statement: bool = False,
) -> list[dict[str, str]]:
    sections = [
        f'<fixed_context path="{safe_display_name(file_name)}">',
        source,
        "</fixed_context>",
        "",
        "<task_plan>",
        task_plan,
        "</task_plan>",
        "",
    ]
    if include_problem_statement and problem_statement.strip():
        sections.extend(["<problem_statement>", problem_statement, "</problem_statement>", ""])
    sections.extend(["<task>", EXECUTOR_TASK_PROMPT, "</task>"])
    return [
        {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(sections)},
    ]


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(
    input_file: Path,
    output_dir: Path,
    *,
    planner_model: str,
    executor_model: str,
    planner_api_key: str | None = None,
    executor_api_key: str | None = None,
    planner_base_url: str | None = None,
    executor_base_url: str | None = None,
    planner_temperature: float = 0.2,
    executor_temperature: float = 0.0,
    planner_max_tokens: int = 8_192,
    executor_max_tokens: int = 65_536,
    timeout: float = 1_800.0,
    api_retries: int = 3,
    include_problem_statement: bool = False,
) -> dict[str, object]:
    source = input_file.read_text(encoding="utf-8")
    display_name = safe_display_name(input_file.name)
    output_dir.mkdir(parents=True, exist_ok=True)

    planner = ChatClient(
        model=planner_model,
        api_key=planner_api_key,
        base_url=planner_base_url,
        timeout=timeout,
        max_retries=api_retries,
    )
    planner_messages = build_planner_messages(display_name, source)
    _write_json(output_dir / "planner_messages.json", {"messages": planner_messages})
    planner_generation = planner.complete(
        planner_messages,
        temperature=planner_temperature,
        max_tokens=planner_max_tokens,
    )
    (output_dir / "planner_raw_output.txt").write_text(planner_generation.content, encoding="utf-8")
    task_plan, plan_parse = extract_single_tag(planner_generation.content, "task_plan")
    problem_statement, problem_parse = extract_single_tag(
        planner_generation.content, "problem_statement"
    )
    if plan_parse["status"] != "ok":
        result = {
            "mode": "task_plan",
            "target_file": display_name,
            "planner_model": planner_model,
            "executor_model": executor_model,
            "status": "planner_parse_failed",
            "planner_parse": plan_parse,
            "problem_statement_parse": problem_parse,
            "patch_applied": False,
        }
        _write_json(output_dir / "result.json", result)
        return result

    (output_dir / "task_plan.txt").write_text(task_plan, encoding="utf-8")
    if problem_parse["status"] == "ok":
        (output_dir / "problem_statement.txt").write_text(problem_statement, encoding="utf-8")

    executor_messages = build_executor_messages(
        display_name,
        source,
        task_plan,
        problem_statement,
        include_problem_statement,
    )
    _write_json(output_dir / "executor_messages.json", {"messages": executor_messages})
    executor = ChatClient(
        model=executor_model,
        api_key=executor_api_key or planner_api_key,
        base_url=executor_base_url or planner_base_url,
        timeout=timeout,
        max_retries=api_retries,
    )
    executor_generation = executor.complete(
        executor_messages,
        temperature=executor_temperature,
        max_tokens=executor_max_tokens,
    )
    (output_dir / "executor_raw_output.txt").write_text(executor_generation.content, encoding="utf-8")
    modified, executor_parse = extract_single_tag(executor_generation.content, "modified_file")
    if executor_parse["status"] != "ok":
        result = {
            "mode": "task_plan",
            "target_file": display_name,
            "planner_model": planner_model,
            "executor_model": executor_model,
            "status": "executor_parse_failed",
            "planner_parse": plan_parse,
            "problem_statement_parse": problem_parse,
            "executor_parse": executor_parse,
            "patch_applied": False,
        }
        _write_json(output_dir / "result.json", result)
        return result

    (output_dir / "modified_file").write_text(modified.rstrip("\n") + "\n", encoding="utf-8")
    patch = make_unified_diff(display_name, source, modified.rstrip("\n") + "\n")
    if not patch:
        result = {
            "mode": "task_plan",
            "target_file": display_name,
            "planner_model": planner_model,
            "executor_model": executor_model,
            "status": "empty_injection_patch",
            "planner_parse": plan_parse,
            "problem_statement_parse": problem_parse,
            "executor_parse": executor_parse,
            "patch_applied": False,
        }
        _write_json(output_dir / "result.json", result)
        return result

    applied, modified_or_error, details = apply_patch_safely(display_name, source, patch)
    result = {
        "mode": "task_plan",
        "target_file": display_name,
        "planner_model": planner_model,
        "executor_model": executor_model,
        "status": "ok" if applied else "patch_rejected",
        "planner_parse": plan_parse,
        "problem_statement_parse": problem_parse,
        "executor_parse": executor_parse,
        "patch_applied": applied,
        "patch_stats": patch_stats(patch),
        "patch_apply_details": details,
    }
    if applied:
        (output_dir / "injection.patch").write_text(patch, encoding="utf-8")
        (output_dir / "injected_file").write_text(str(modified_or_error), encoding="utf-8")
        result["patch"] = "injection.patch"
        result["injected_file"] = "injected_file"
    else:
        result["error"] = str(modified_or_error)
    _write_json(output_dir / "result.json", result)
    return result
