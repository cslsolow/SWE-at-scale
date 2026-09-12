# FreeSWE single-file issue injection

FreeSWE provides two independent pipelines for creating a single-file
SWE-style issue from a correct source file:

```text
Numbered Fixed: fixed source -> line-numbered prompt -> issue patch
Task Plan:      fixed source -> task plan/problem statement
                -> executor modified file -> issue patch
```

Both pipelines validate that the result is a single-file, applyable patch and
write the injected file plus the unified diff. The Task Plan pipeline includes
the planner/executor split used by the corresponding Stage 5 data format.

## Privacy and release policy

This repository is intentionally self-contained and provider-neutral:

- No API key, token, private endpoint, server hostname, checkpoint, benchmark
  row, trajectory, or experiment log is included.
- The client uses the official OpenAI SDK defaults when no runtime base URL is
  supplied. A compatible endpoint can be selected through an environment
  variable at run time; it is not embedded in the source or examples.
- Absolute input paths are reduced to a safe file name before entering a model
  prompt or result metadata. Output metadata never records the caller's home
  directory.
- Credentials are read from environment variables only. Do not put a real key
  in `.env.example`, shell history, source files, or committed output files.

The code is designed for public release, but users remain responsible for
checking the source files they feed to a model for proprietary content.

## Installation

Python 3.10 or newer is required. Install into a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

Set credentials and model identifiers at runtime. The package does not choose a
checkpoint or model on your behalf:

```bash
export OPENAI_API_KEY='...'
```

For a compatible local server, set `OPENAI_BASE_URL` only in the runtime
environment. Do not commit that value.

## Numbered Fixed

The input is the original, unnumbered source file. FreeSWE adds reference line
numbers only inside the prompt. The model must return a unified diff against
the original file, wrapped in `<issue_patch>...</issue_patch>`.

```bash
export NUMBERED_FIXED_MODEL='your-numbered-fixed-model'
freeswe numbered-fixed \
  --model "$NUMBERED_FIXED_MODEL" \
  --input examples/fixed_context.py \
  --output-dir outputs/numbered_fixed
```

On success, the output directory contains:

```text
injected_file       # patched source file
injection.patch     # applyable unified diff
messages.json       # sanitized model messages
result.json         # status and patch statistics
```

The patch is first applied normally with `git apply`. If that fails, the
runner retries with `git apply --recount`. A reverse-apply roundtrip is
required before the result is accepted.

## Task Plan plus executor

The planner receives the fixed source and must return both
`<task_plan>...</task_plan>` and `<problem_statement>...</problem_statement>`.
The executor receives the fixed source and task plan and must return the
complete modified file in `<modified_file>...</modified_file>`. The executor
does not receive the problem statement by default, matching the task-plan
implementation format; pass `--include-problem-statement` only when that
variant is intentional.

```bash
export TASK_PLAN_MODEL='your-task-plan-model'
export TASK_PLAN_EXECUTOR_MODEL='your-executor-model'
freeswe task-plan \
  --planner-model "$TASK_PLAN_MODEL" \
  --executor-model "$TASK_PLAN_EXECUTOR_MODEL" \
  --input examples/fixed_context.py \
  --output-dir outputs/task_plan
```

On success, the output directory additionally contains:

```text
task_plan.txt
problem_statement.txt
modified_file
injected_file
injection.patch
planner_messages.json
executor_messages.json
result.json
```

The generated diff is created locally from the fixed and modified files, then
validated with the same forward/reverse apply check as Numbered Fixed.

## Runtime configuration

The following values are deliberately runtime-only:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | API credential |
| `OPENAI_BASE_URL` | Optional compatible endpoint override |
| `OPENAI_MODEL` | Fallback model identifier |
| `NUMBERED_FIXED_MODEL` | Numbered Fixed model identifier |
| `TASK_PLAN_MODEL` | Planner model identifier |
| `TASK_PLAN_EXECUTOR_MODEL` | Executor model identifier |

Command-line model options take precedence over environment variables. The
package never writes these values to `result.json`.

## Development checks

```bash
python -m pip install -e .
python -m pytest -q
```

The tests use a fake client and do not call any remote service.

## Scope

The public package currently supports single-file inference and local patch
validation. Repository-level Docker evaluation, benchmark data, checkpoint
hosting, and service deployment are intentionally outside this release so that
the repository remains reproducible and free of private infrastructure details.
