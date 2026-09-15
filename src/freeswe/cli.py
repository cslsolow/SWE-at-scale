"""Command-line interface for the FreeSWE issue-injection pipelines."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .numbered_fixed import run as run_numbered_fixed
from .task_plan import run as run_task_plan


def _required_model(value: str | None, env_names: tuple[str, ...]) -> str:
    model = value
    if not model:
        for env_name in (*env_names, "OPENAI_MODEL"):
            model = os.getenv(env_name)
            if model:
                break
    if not model:
        names = "/".join((*env_names, "OPENAI_MODEL"))
        raise SystemExit(f"model is required; pass the option or set {names}")
    return model


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", type=Path, required=True, help="fixed source file")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--api-retries", type=int, default=3)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="freeswe",
        description="Generate an SWE-style issue with FreeSWE or FreeSWE+.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    numbered = subparsers.add_parser(
        "free-swe",
        aliases=["numbered-fixed"],
        help="FreeSWE: direct issue-patch generation",
    )
    _common(numbered)
    numbered.add_argument("--model")
    numbered.add_argument("--base-url", help="optional runtime OpenAI-compatible base URL")
    numbered.add_argument("--temperature", type=float, default=0.0)
    numbered.add_argument("--max-tokens", type=int, default=16_384)

    planner = subparsers.add_parser(
        "free-swe-plus",
        aliases=["task-plan"],
        help="FreeSWE+: planner/executor issue generation",
    )
    _common(planner)
    planner.add_argument("--planner-model")
    planner.add_argument("--executor-model")
    planner.add_argument("--planner-base-url", help="optional runtime base URL for planner")
    planner.add_argument("--executor-base-url", help="optional runtime base URL for executor")
    planner.add_argument("--planner-temperature", type=float, default=0.2)
    planner.add_argument("--executor-temperature", type=float, default=0.0)
    planner.add_argument("--planner-max-tokens", type=int, default=8_192)
    planner.add_argument("--executor-max-tokens", type=int, default=65_536)
    planner.add_argument(
        "--include-problem-statement",
        action="store_true",
        help="also give the generated problem statement to the executor",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in {"free-swe", "numbered-fixed"}:
        result = run_numbered_fixed(
            args.input,
            args.output_dir,
            model=_required_model(args.model, ("FREESWE_MODEL", "NUMBERED_FIXED_MODEL")),
            base_url=args.base_url,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            api_retries=args.api_retries,
        )
    else:
        result = run_task_plan(
            args.input,
            args.output_dir,
            planner_model=_required_model(
                args.planner_model,
                ("FREESWE_PLUS_PLANNER_MODEL", "TASK_PLAN_MODEL"),
            ),
            executor_model=_required_model(
                args.executor_model,
                ("FREESWE_PLUS_EXECUTOR_MODEL", "TASK_PLAN_EXECUTOR_MODEL"),
            ),
            planner_base_url=args.planner_base_url,
            executor_base_url=args.executor_base_url,
            planner_temperature=args.planner_temperature,
            executor_temperature=args.executor_temperature,
            planner_max_tokens=args.planner_max_tokens,
            executor_max_tokens=args.executor_max_tokens,
            timeout=args.timeout,
            api_retries=args.api_retries,
            include_problem_statement=args.include_problem_statement,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
